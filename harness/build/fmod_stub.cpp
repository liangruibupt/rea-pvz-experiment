// Operator-only silent FMOD stub for the aarch64 port.
// cocos2d-x v4 ships an x86-64-only proprietary libfmod.so; audio has no gameplay effect in this
// game, so every call succeeds and produces no sound. Channel "finished" callbacks never fire.
#include <cstdint>
#include <cstring>
#include <map>
#include <mutex>
#include "fmod.hpp"

namespace {
std::mutex g_mu;
std::map<const void*, void*> g_user;  // per-object user data
char* fresh() { auto* p = new char[16]; std::memset(p, 0, 16); return p; }
}

extern "C" FMOD_RESULT F_API FMOD_System_Create(FMOD_SYSTEM** system) {
    *system = reinterpret_cast<FMOD_SYSTEM*>(fresh());
    return FMOD_OK;
}

namespace FMOD {
FMOD_RESULT F_API System::release() { return FMOD_OK; }
FMOD_RESULT F_API System::setOutput(FMOD_OUTPUTTYPE) { return FMOD_OK; }
FMOD_RESULT F_API System::init(int, FMOD_INITFLAGS, void*) { return FMOD_OK; }
FMOD_RESULT F_API System::update() { return FMOD_OK; }
FMOD_RESULT F_API System::createSound(const char*, FMOD_MODE, FMOD_CREATESOUNDEXINFO*, Sound** sound) {
    *sound = reinterpret_cast<Sound*>(fresh());
    return FMOD_OK;
}
FMOD_RESULT F_API System::playSound(Sound*, ChannelGroup*, bool, Channel** channel) {
    *channel = reinterpret_cast<Channel*>(fresh());
    return FMOD_OK;
}

FMOD_RESULT F_API Sound::release() { return FMOD_OK; }
FMOD_RESULT F_API Sound::getLength(unsigned int* length, FMOD_TIMEUNIT) { *length = 0; return FMOD_OK; }
FMOD_RESULT F_API Sound::setUserData(void* d) { std::lock_guard<std::mutex> l(g_mu); g_user[this] = d; return FMOD_OK; }
FMOD_RESULT F_API Sound::getUserData(void** d) { std::lock_guard<std::mutex> l(g_mu); *d = g_user[this]; return FMOD_OK; }

FMOD_RESULT F_API ChannelControl::stop() { return FMOD_OK; }
FMOD_RESULT F_API ChannelControl::setPaused(bool) { return FMOD_OK; }
FMOD_RESULT F_API ChannelControl::setVolume(float) { return FMOD_OK; }
FMOD_RESULT F_API ChannelControl::setMode(FMOD_MODE) { return FMOD_OK; }
FMOD_RESULT F_API ChannelControl::setCallback(FMOD_CHANNELCONTROL_CALLBACK) { return FMOD_OK; }
FMOD_RESULT F_API ChannelControl::setUserData(void* d) { std::lock_guard<std::mutex> l(g_mu); g_user[this] = d; return FMOD_OK; }
FMOD_RESULT F_API ChannelControl::getUserData(void** d) { std::lock_guard<std::mutex> l(g_mu); *d = g_user[this]; return FMOD_OK; }

FMOD_RESULT F_API Channel::setLoopCount(int) { return FMOD_OK; }
FMOD_RESULT F_API Channel::setPosition(unsigned int, FMOD_TIMEUNIT) { return FMOD_OK; }
FMOD_RESULT F_API Channel::getPosition(unsigned int* p, FMOD_TIMEUNIT) { *p = 0; return FMOD_OK; }
}  // namespace FMOD
