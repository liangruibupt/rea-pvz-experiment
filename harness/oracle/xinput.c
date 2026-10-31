// XTest input injection for the oracle shim (kept apart from cocos headers: X11 macros clash).
#include <X11/Xlib.h>
#include <X11/extensions/XTest.h>
#include <string.h>

static Display* dpy;
static int win_x, win_y;

static Window find_window(Display* d, Window w, const char* title) {
    char* name = NULL;
    if (XFetchName(d, w, &name) && name) {
        int hit = strcmp(name, title) == 0;
        XFree(name);
        if (hit) return w;
    }
    Window root, parent, *kids = NULL;
    unsigned n = 0;
    if (!XQueryTree(d, w, &root, &parent, &kids, &n)) return 0;
    Window found = 0;
    for (unsigned i = 0; i < n && !found; ++i) found = find_window(d, kids[i], title);
    if (kids) XFree(kids);
    return found;
}

static int ensure(void) {
    if (dpy) return 1;
    dpy = XOpenDisplay(NULL);
    if (!dpy) return 0;
    Window w = find_window(dpy, DefaultRootWindow(dpy), "pvz");
    if (w) {
        Window child;
        XTranslateCoordinates(dpy, w, DefaultRootWindow(dpy), 0, 0, &win_x, &win_y, &child);
    }
    return 1;
}

// x, y: window pixels, top-left origin
int xin_inject(char kind, int x, int y) {
    if (!ensure()) return 0;
    XTestFakeMotionEvent(dpy, -1, win_x + x, win_y + y, CurrentTime);
    if (kind == 'd') XTestFakeButtonEvent(dpy, 1, True, CurrentTime);
    if (kind == 'u') XTestFakeButtonEvent(dpy, 1, False, CurrentTime);
    return 1;
}

void xin_flush(void) {
    if (dpy) XSync(dpy, False);
}
