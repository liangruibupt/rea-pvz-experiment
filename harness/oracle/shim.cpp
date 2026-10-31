// pvz oracle shim (operator only). LD_PRELOAD into the UNMODIFIED stripped pvz ELF.
//
//  * Virtual clock: CLOCK_MONOTONIC/REALTIME, gettimeofday and time() are virtual. Only the main
//    thread's usleep() (the cocos frame limiter in Application::run) advances it, by exactly the
//    requested amount, so every frame is a fixed step. That usleep is the frame boundary.
//  * Entropy: time() returns PVZ_TIME_SEED (+ whole virtual seconds since level start).
//    std::random_device::_M_getval() returns a documented splitmix64 stream seeded with
//    PVZ_DEVICE_SEED and restarted at level start. Level start = the srand() call made by the
//    GSControlLayer constructor (identified by return address via operator-only symbols).
//  * Input: XTest events injected at frame boundaries (glfw reads them in the next pollEvents).
//  * Trace: after level start, a JSON snapshot per boundary is read from live game objects
//    (layout from the game headers; addresses from the operator's unstripped twin of the ELF).
#include <dlfcn.h>
#include <link.h>
#include <sys/syscall.h>
#include <sys/time.h>
#include <time.h>
#include <unistd.h>
#include <algorithm>
#include <cmath>
#include <cstdint>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <fstream>
#include <list>
#include <map>
#include <random>
#include <sstream>
#include <string>
#include <unordered_map>
#include <vector>

#define private public
#define protected public
#include "cocos2d.h"
#include "spine/spine-cocos2dx.h"
#include "ui/CocosGUI.h"
#include "Based/Runtime.h"
#include "Based/Car.h"
#include "Plants/Plants.h"
#include "Plants/DefensePlants/Sun.h"
#include "Plants/EmissonPlants/Bullet/Bullet.h"
#include "Scenes/GameScene/GSButtonLayer.h"
#include "Scenes/GameScene/GSControlLayer.h"
#include "Scenes/GameScene/ZombiesAppearControl.h"
#include "Zombies/Zombies.h"
#undef private
#undef protected

namespace {

struct Sym { uintptr_t off; size_t size; };
std::unordered_map<std::string, Sym> g_syms __attribute__((init_priority(101)));
uintptr_t g_base = 0;

int phdr_cb(struct dl_phdr_info* info, size_t, void*) {
    if (g_base == 0 && (info->dlpi_name == nullptr || info->dlpi_name[0] == 0)) g_base = info->dlpi_addr;
    return 0;
}
void* addr_of(const char* name) {
    auto it = g_syms.find(name);
    if (it == g_syms.end()) {  // std::list globals carry the [abi:cxx11] tag
        std::string n(name);
        it = g_syms.find("_Z" + std::to_string(n.size()) + n + "B5cxx11");
    }
    if (it == g_syms.end()) { fprintf(stderr, "[shim] missing symbol %s\n", name); _exit(90); }
    return reinterpret_cast<void*>(g_base + it->second.off);
}
bool in_sym(uintptr_t pc, const char* name) {
    auto it = g_syms.find(name);
    if (it == g_syms.end()) return false;
    uintptr_t a = g_base + it->second.off;
    return pc >= a && pc < a + it->second.size;
}

using clock_gettime_t = int (*)(clockid_t, struct timespec*);
using gettimeofday_t = int (*)(struct timeval*, void*);
using usleep_t = int (*)(useconds_t);
using srand_t = void (*)(unsigned);
clock_gettime_t real_clock_gettime;
gettimeofday_t real_gettimeofday;
usleep_t real_usleep;
srand_t real_srand;

bool g_ready = false;
pid_t g_main_tid = 0;
int64_t g_vt_ns = 1000000000LL;  // virtual monotonic clock
const int64_t kRealtimeEpochNs = 1700000000LL * 1000000000LL;
long g_time_seed = 1700000000;
uint64_t g_device_seed = 1;
uint64_t g_device_state = 0;
bool g_level_started = false;
int64_t g_level_start_vt = 0;
long g_frame = 0;
long g_gframe = -1;
long g_end_frame = 6000;
long g_post_result_frames = 60;
long g_boot_max = 20000;
long g_result_at = -1;
FILE* g_trace = nullptr;
FILE* g_events_out = nullptr;

struct Input { char kind; int x, y; };  // m=move d=down u=up
std::multimap<long, Input> g_inputs __attribute__((init_priority(101)));    // keyed by game frame

struct BootStep { std::string scene; long delay; char kind; int x, y; };
std::vector<BootStep> g_boot __attribute__((init_priority(101)));
size_t g_boot_i = 0;
void* g_last_scene = nullptr;
long g_scene_frames = 0;

struct Plan { long frame; int card, row, col; };
std::vector<Plan> g_plan __attribute__((init_priority(101)));
bool g_bot = false;
bool g_bot_collect_sun = false;
long g_bot_sun_every = 30;
std::mt19937 g_bot_rng __attribute__((init_priority(101)))(7);

uint64_t splitmix64(uint64_t& s) {
    uint64_t z = (s += 0x9E3779B97F4A7C15ULL);
    z = (z ^ (z >> 30)) * 0xBF58476D1CE4E5B9ULL;
    z = (z ^ (z >> 27)) * 0x94D049BB133111EBULL;
    return z ^ (z >> 31);
}

void load_syms(const char* path) {
    std::ifstream in(path);
    std::string name, off;
    size_t size;
    while (in >> name >> off >> size) g_syms[name] = Sym{std::stoull(off, nullptr, 16), size};
    if (g_syms.empty()) { fprintf(stderr, "[shim] no symbols in %s\n", path ? path : "(null)"); _exit(91); }
}

// Scenario format (one directive per line, '#' comments):
//   time_seed <n> | device_seed <n> | end_frame <n> | post_result_frames <n>
//   boot <SceneVtableSymbol> <delay_frames> <m|d|u> <x> <y>   (x,y window px, top-left origin)
//   input <game_frame> <m|d|u> <x> <y>
//   bot_plant <game_frame> <card_index> <row> <col>            (operator generator only)
//   bot_collect_sun <every_n_frames>                            (operator generator only)
void load_scenario(const char* path) {
    std::ifstream in(path);
    std::string line;
    while (std::getline(in, line)) {
        if (line.empty() || line[0] == '#') continue;
        std::istringstream ss(line);
        std::string k;
        ss >> k;
        if (k == "time_seed") ss >> g_time_seed;
        else if (k == "device_seed") ss >> g_device_seed;
        else if (k == "end_frame") ss >> g_end_frame;
        else if (k == "post_result_frames") ss >> g_post_result_frames;
        else if (k == "boot_max") ss >> g_boot_max;
        else if (k == "boot") { BootStep b; ss >> b.scene >> b.delay >> b.kind >> b.x >> b.y; g_boot.push_back(b); }
        else if (k == "input") { long f; Input i; ss >> f >> i.kind >> i.x >> i.y; g_inputs.emplace(f, i); }
        else if (k == "bot_plant") { Plan p; ss >> p.frame >> p.card >> p.row >> p.col; g_plan.push_back(p); g_bot = true; }
        else if (k == "bot_collect_sun") { ss >> g_bot_sun_every; g_bot_collect_sun = true; g_bot = true; }
        else if (k == "bot_seed") { unsigned s; ss >> s; g_bot_rng.seed(s); }
    }
}

}  // namespace

namespace {

// ---------------------------------------------------------------- X input (xinput.c)
extern "C" int xin_inject(char kind, int x, int y);
extern "C" void xin_flush(void);
void inject(const Input& in) { xin_inject(in.kind, in.x, in.y); }
bool g_injected = false;
void flush_inputs() {
    xin_flush();
    // Real (not virtual) settle time so the X server delivers events to glfw's connection
    // before the game's next pollEvents. Does not advance the virtual clock.
    real_usleep(15000);
}

// ---------------------------------------------------------------- snapshot
std::unordered_map<const void*, int> g_zid __attribute__((init_priority(101))), g_pid __attribute__((init_priority(101))), g_bid __attribute__((init_priority(101))), g_sid __attribute__((init_priority(101)));
int g_next_zid = 1, g_next_pid = 1, g_next_bid = 1, g_next_sid = 1;

int stable_id(std::unordered_map<const void*, int>& m, int& next, const void* p) {
    auto it = m.find(p);
    if (it != m.end()) return it->second;
    m[p] = next;
    return next++;
}

template <class T>
void prune(std::unordered_map<const void*, int>& m, const std::vector<const T*>& live) {
    for (auto it = m.begin(); it != m.end();) {
        if (std::find(live.begin(), live.end(), static_cast<const T*>(it->first)) == live.end()) it = m.erase(it);
        else ++it;
    }
}

const char* ztype(ZombiesType t) {
    switch (t) {
        case ZombiesType::CommonZombies: return "common";
        case ZombiesType::ConeZombies: return "cone";
        case ZombiesType::BucketZombies: return "bucket";
        case ZombiesType::CommonFlagZombies: return "flag";
        default: return "none";
    }
}
const char* ptype(PlantsType t) {
    switch (t) {
        case PlantsType::SunFlower: return "sunflower";
        case PlantsType::PeaShooter: return "peashooter";
        case PlantsType::WallNut: return "wallnut";
        default: return "none";
    }
}

std::string fx(double v) {  // fixed 3-decimals, stable formatting
    char b[48];
    std::snprintf(b, sizeof b, "%.3f", v);
    return b;
}

struct SunSeen { int id; float x, y; bool enabled; };
std::vector<SunSeen> g_last_suns __attribute__((init_priority(101)));

void snapshot(long gf) {
    auto* runtime = *reinterpret_cast<Runtime**>(addr_of("_ZN7Runtime9_instanceE"));
    auto& world = runtime->userData->_userWorldData;
    auto* control = *reinterpret_cast<GSControlLayer**>(addr_of("controlLayerInformation"));
    auto* buttons = *reinterpret_cast<GSButtonLayer**>(addr_of("buttonLayerInformation"));
    auto& zombies = *reinterpret_cast<std::list<Zombies*>*>(addr_of("ZombiesGroup"));
    auto& plants = *reinterpret_cast<std::multimap<int, Plants*>*>(addr_of("PlantsGroup"));
    auto& bullets = *reinterpret_cast<std::list<Bullet*>*>(addr_of("BulletGroup"));
    auto& suns = *reinterpret_cast<std::list<Sun*>*>(addr_of("SunsGroup"));
    auto& cars = *reinterpret_cast<std::list<Car*>*>(addr_of("CarsGroup"));
    bool zombie_win = *reinterpret_cast<bool*>(addr_of("_ZN7Zombies12_zombieIsWinE"));
    auto* director = *reinterpret_cast<cocos2d::Director**>(addr_of("_ZN7cocos2dL16s_SharedDirectorE"));

    std::ostringstream o;
    o << "{\"f\":" << gf << ",\"sun\":" << world.sunNumbers;
    if (director && director->_scheduler) o << ",\"ts\":" << fx(director->_scheduler->_timeScale);
    if (control && control->_zombiesAppearControl) {
        auto* z = control->_zombiesAppearControl;
        o << ",\"wave\":" << z->_zombiesAppearFrequency << ",\"wt\":" << fx(z->_time)
          << ",\"wbegin\":" << (z->_isBegin ? 1 : 0) << ",\"wdead\":" << (z->_lastFrequencyZombiesWasDeath ? 1 : 0);
    }
    o << ",\"end\":" << ((control && control->_gameEndShieldLayer) ? 1 : 0) << ",\"zwin\":" << (zombie_win ? 1 : 0);

    if (buttons) {
        o << ",\"cards\":[";
        bool first = true;
        for (auto& c : world.userSelectCard) {
            auto& pc = buttons->plantsCards[c.cardTag];
            if (!first) o << ',';
            first = false;
            o << "{\"tag\":" << c.cardTag << ",\"ready\":" << (pc.timeBarIsFinished ? 1 : 0)
              << ",\"pct\":" << fx(pc.progressTimer ? pc.progressTimer->_percentage : -1)
              << ",\"en\":" << ((pc.plantsCards && pc.plantsCards->_enabled) ? 1 : 0) << '}';
        }
        o << "]";
        if (buttons->mouseSelectImage) {
            auto* m = buttons->mouseSelectImage;
            o << ",\"hold\":" << (m->isSelectPlants ? static_cast<int>(m->selectPlantsId) : -1)
              << ",\"shovel\":" << (m->isSelectShovel ? 1 : 0);
        }
    }

    std::vector<const Zombies*> zl;
    o << ",\"z\":[";
    bool first = true;
    for (auto* z : zombies) {
        zl.push_back(z);
        if (!first) o << ',';
        first = false;
        o << "{\"id\":" << stable_id(g_zid, g_next_zid, z) << ",\"t\":\"" << ztype(z->_zombiesType)
          << "\",\"x\":" << fx(z->getZombiePositionX()) << ",\"y\":" << fx(z->getZombiePositionY())
          << ",\"hp\":" << fx(z->_currentBloodVolume) << ",\"hs\":" << fx(z->_currentHeadShieldVolume)
          << ",\"bs\":" << fx(z->_currentBodyShieldVolume) << ",\"eat\":" << (z->_isEat ? 1 : 0)
          << ",\"alive\":" << (z->getZombieIsSurvive() ? 1 : 0) << ",\"show\":" << (z->_isShow ? 1 : 0)
          << ",\"spd\":" << fx(z->_currentSpeed) << '}';
    }
    o << "]";
    prune(g_zid, zl);

    std::vector<const Plants*> pl;
    o << ",\"p\":[";
    first = true;
    for (auto& kv : plants) {
        auto* p = kv.second;
        pl.push_back(p);
        if (!first) o << ',';
        first = false;
        o << "{\"id\":" << stable_id(g_pid, g_next_pid, p) << ",\"t\":\"" << ptype(p->_plantsType)
          << "\",\"r\":" << static_cast<int>(p->_rowAndColumn.x) << ",\"c\":" << static_cast<int>(p->_rowAndColumn.y)
          << ",\"hp\":" << fx(p->_healthPoint) << '}';
    }
    o << "]";
    prune(g_pid, pl);

    std::vector<const Bullet*> bl;
    o << ",\"b\":[";
    first = true;
    for (auto* b : bullets) {
        bl.push_back(b);
        if (!first) o << ',';
        first = false;
        o << "{\"id\":" << stable_id(g_bid, g_next_bid, b) << ",\"x\":" << fx(b->getBulletPositionX())
          << ",\"y\":" << fx(b->getBulletPositionY()) << ",\"used\":" << (b->_isUsed ? 1 : 0) << '}';
    }
    o << "]";
    prune(g_bid, bl);

    std::vector<const Sun*> sl;
    g_last_suns.clear();
    o << ",\"s\":[";
    first = true;
    for (auto* s : suns) {
        sl.push_back(s);
        float x = s->_sun ? s->_sun->getPositionX() : 0, y = s->_sun ? s->_sun->getPositionY() : 0;
        int id = stable_id(g_sid, g_next_sid, s);
        g_last_suns.push_back({id, x, y, s->_isEnable});
        if (!first) o << ',';
        first = false;
        o << "{\"id\":" << id << ",\"x\":" << fx(x) << ",\"y\":" << fx(y) << ",\"en\":" << (s->_isEnable ? 1 : 0) << '}';
    }
    o << "]";
    prune(g_sid, sl);

    o << ",\"cars\":[";
    first = true;
    for (auto* c : cars) {
        if (!first) o << ',';
        first = false;
        o << "{\"tag\":" << c->_tag << ",\"live\":" << (c->_isLive ? 1 : 0) << ",\"st\":" << c->_carState
          << ",\"x\":" << fx(c->_carImage ? c->_carImage->getPositionX() : 0) << '}';
    }
    o << "]}\n";
    std::fputs(o.str().c_str(), g_trace);
    // The target aborts (glibc fortify, SIGABRT) on its own loss path; flush per frame so
    // the trace ends at the last complete frame deterministically instead of at a random
    // stdio buffer boundary.
    std::fflush(g_trace);
    if (g_events_out) std::fflush(g_events_out);
    if (zombie_win || (control && control->_gameEndShieldLayer)) {
        if (g_result_at < 0) g_result_at = gf;
    }
}

}  // namespace

namespace {

void* running_scene() {
    auto* director = *reinterpret_cast<cocos2d::Director**>(addr_of("_ZN7cocos2dL16s_SharedDirectorE"));
    return director ? director->_runningScene : nullptr;
}
bool scene_is(void* scene, const std::string& cls) {
    if (!scene) return false;
    std::string vt = "_ZTV" + std::to_string(cls.size()) + cls;
    auto it = g_syms.find(vt);
    if (it == g_syms.end()) return false;
    uintptr_t vptr = *reinterpret_cast<uintptr_t*>(scene);
    return vptr == g_base + it->second.off + 2 * sizeof(void*);
}

std::multimap<long, Input> g_pending_abs __attribute__((init_priority(101)));  // absolute-frame queue (boot clicks' release)

void record(long gf, const Input& in) {
    if (g_events_out) std::fprintf(g_events_out, "input %ld %c %d %d\n", gf, in.kind, in.x, in.y);
}
void click_at(long gf, int x, int y) {  // down now, up on the next game frame
    g_inputs.emplace(gf, Input{'d', x, y});
    g_inputs.emplace(gf + 1, Input{'u', x, y});
}

// design coordinates (1920x1080, bottom-left origin) -> window pixels (1280x720, top-left origin)
int wx(double xd) { return static_cast<int>(std::lround(xd * 1280.0 / 1920.0)); }
int wy(double yd) { return static_cast<int>(std::lround((1080.0 - yd) * 720.0 / 1080.0)); }
// The game resolves the hovered lawn cell in a 0.1 s schedule, so the bot hovers first.
void hover_click(long gf, int x, int y, long settle) {
    g_inputs.emplace(gf, Input{'m', x, y});
    click_at(gf + settle, x, y);
}

void run_bot(long gf) {
    for (auto& p : g_plan) {
        if (p.frame == gf) {
            hover_click(gf, wx(105), wy(1008 - 103 * p.card), 2);
            hover_click(gf + 4, wx(570 + 122 * p.col + 61), wy(110 + 140 * p.row + 70), 10);
        }
    }
    if (g_bot_collect_sun && gf > 0 && gf % g_bot_sun_every == 0) {
        for (auto& s : g_last_suns) {
            if (!s.enabled) continue;
            int x = wx(s.x), y = wy(s.y);
            if (x > 0 && x < 1280 && y > 0 && y < 720) { hover_click(gf, x, y, 2); break; }
        }
    }
}

void finish(int code) {
    if (g_trace) std::fflush(g_trace);
    if (g_events_out) std::fflush(g_events_out);
    _exit(code);
}

void on_boundary() {
    ++g_frame;
    bool any = false;
    if (!g_level_started) {
        void* sc = running_scene();
        if (sc != g_last_scene) {
            g_last_scene = sc; g_scene_frames = 0;
            std::string cls = "?";
            if (sc) {
                uintptr_t vt = *reinterpret_cast<uintptr_t*>(sc) - 2 * sizeof(void*) - g_base;
                for (auto& kv : g_syms) if (kv.second.off == vt && kv.first.rfind("_ZTV", 0) == 0) { cls = kv.first; break; }
            }
            std::fprintf(stderr, "[shim] frame %ld scene %s\n", g_frame, cls.c_str());
        } else ++g_scene_frames;
        auto r = g_pending_abs.equal_range(g_frame);
        for (auto it = r.first; it != r.second; ++it) { inject(it->second); any = true; }
        g_pending_abs.erase(r.first, r.second);
        if (g_boot_i < g_boot.size()) {
            auto& b = g_boot[g_boot_i];
            if (scene_is(sc, b.scene) && g_scene_frames >= b.delay) {
                if (b.kind == 'c') {
                    inject(Input{'d', b.x, b.y});
                    g_pending_abs.emplace(g_frame + 1, Input{'u', b.x, b.y});
                } else {
                    inject(Input{b.kind, b.x, b.y});
                }
                any = true;
                ++g_boot_i;
                g_scene_frames = 0;
            }
        }
        if (g_frame > g_boot_max) { std::fprintf(stderr, "[shim] boot timeout at step %zu\n", g_boot_i); finish(92); }
    } else {
        ++g_gframe;
        if (g_gframe > 0 && !scene_is(running_scene(), "GameScene")) {
            std::fprintf(stderr, "[shim] game scene left at game frame %ld\n", g_gframe);
            finish(3);
        }
        snapshot(g_gframe);
        if (g_bot) run_bot(g_gframe);
        auto r = g_inputs.equal_range(g_gframe);
        for (auto it = r.first; it != r.second; ++it) {
            Input in = it->second;
            if (in.kind == 'c') {  // sugar: click = down now, up next frame
                in.kind = 'd';
                g_inputs.emplace(g_gframe + 1, Input{'u', in.x, in.y});
            }
            record(g_gframe, in);
            inject(in);
            any = true;
        }
        if (g_gframe >= g_end_frame) finish(0);
        if (g_result_at >= 0 && g_gframe >= g_result_at + g_post_result_frames) finish(0);
    }
    if (any) flush_inputs();
}

}  // namespace

// ---------------------------------------------------------------- interposed symbols
extern "C" {

__attribute__((visibility("default"))) int clock_gettime(clockid_t id, struct timespec* ts) {
    if (!g_ready) {
        if (!real_clock_gettime) real_clock_gettime = (clock_gettime_t)dlsym(RTLD_NEXT, "clock_gettime");
        return real_clock_gettime(id, ts);
    }
    int64_t ns;
    switch (id) {
        case CLOCK_MONOTONIC: case CLOCK_MONOTONIC_RAW: case CLOCK_MONOTONIC_COARSE: case CLOCK_BOOTTIME:
            ns = g_vt_ns; break;
        case CLOCK_REALTIME: case CLOCK_REALTIME_COARSE:
            ns = kRealtimeEpochNs + g_vt_ns; break;
        default: return real_clock_gettime(id, ts);
    }
    ts->tv_sec = ns / 1000000000LL;
    ts->tv_nsec = ns % 1000000000LL;
    return 0;
}

__attribute__((visibility("default"))) int gettimeofday(struct timeval* tv, void* tz) {
    if (!g_ready) {
        if (!real_gettimeofday) real_gettimeofday = (gettimeofday_t)dlsym(RTLD_NEXT, "gettimeofday");
        return real_gettimeofday(tv, tz);
    }
    int64_t ns = kRealtimeEpochNs + g_vt_ns;
    if (tv) { tv->tv_sec = ns / 1000000000LL; tv->tv_usec = (ns % 1000000000LL) / 1000; }
    return 0;
}

__attribute__((visibility("default"))) time_t time(time_t* out) {
    time_t t = g_time_seed;
    if (g_level_started) t += static_cast<time_t>((g_vt_ns - g_level_start_vt) / 1000000000LL);
    if (out) *out = t;
    return t;
}

__attribute__((visibility("default"))) int usleep(useconds_t us) {
    if (!real_usleep) real_usleep = (usleep_t)dlsym(RTLD_NEXT, "usleep");
    if (!g_ready || static_cast<pid_t>(syscall(SYS_gettid)) != g_main_tid) return real_usleep(us);
    g_vt_ns += static_cast<int64_t>(us) * 1000;
    on_boundary();
    return 0;
}

__attribute__((visibility("default"))) void srand(unsigned seed) {
    if (!real_srand) real_srand = (srand_t)dlsym(RTLD_NEXT, "srand");
    uintptr_t pc = reinterpret_cast<uintptr_t>(__builtin_return_address(0));
    if (g_ready && !g_level_started &&
        (in_sym(pc, "_ZN14GSControlLayerC2Ev") || in_sym(pc, "_ZN14GSControlLayerC1Ev"))) {
        g_level_started = true;
        g_level_start_vt = g_vt_ns;
        g_device_state = g_device_seed;
        g_gframe = -1;
    }
    real_srand(seed);
}

// std::random_device::_M_getval()
__attribute__((visibility("default"))) unsigned int pvz_random_device_getval(void*) __asm__("_ZNSt13random_device9_M_getvalEv");
__attribute__((visibility("default"))) unsigned int pvz_random_device_getval(void*) {
    return static_cast<unsigned int>(splitmix64(g_device_state) >> 32);
}

}  // extern "C"

__attribute__((constructor(65000))) static void shim_init() {
    real_clock_gettime = (clock_gettime_t)dlsym(RTLD_NEXT, "clock_gettime");
    real_gettimeofday = (gettimeofday_t)dlsym(RTLD_NEXT, "gettimeofday");
    real_usleep = (usleep_t)dlsym(RTLD_NEXT, "usleep");
    real_srand = (srand_t)dlsym(RTLD_NEXT, "srand");
    // Only act inside the pvz process (LD_PRELOAD is inherited by any helper processes).
    char exe[512] = {0};
    ssize_t n = readlink("/proc/self/exe", exe, sizeof exe - 1);
    if (n <= 0 || std::strcmp(std::strrchr(exe, '/') ? std::strrchr(exe, '/') + 1 : exe, "pvz") != 0) return;
    dl_iterate_phdr(phdr_cb, nullptr);
    load_syms(std::getenv("PVZ_SYMS"));
    if (const char* sc = std::getenv("PVZ_SCENARIO")) load_scenario(sc);
    const char* tr = std::getenv("PVZ_TRACE");
    g_trace = std::fopen(tr ? tr : "/dev/null", "w");
    if (const char* ev = std::getenv("PVZ_EVENTS_OUT")) g_events_out = std::fopen(ev, "w");
    g_device_state = g_device_seed ^ 0xA5A5A5A5A5A5A5A5ULL;  // pre-level stream (not scored)
    g_main_tid = getpid();
    g_ready = true;
}
