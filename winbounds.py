#!/usr/bin/env python3
"""Read a target app's frontmost window rectangle via CoreGraphics (ctypes).

Uses CGWindowListCopyWindowInfo, which returns window owner + bounds WITHOUT
needing Screen Recording permission (only window *titles/contents* need that).
Called through ctypes against the Apple-signed system frameworks, so it sidesteps
the pyobjc Quartz wheel that won't load under the hardened Python runtime.
"""
import ctypes
import ctypes.util
from ctypes import c_void_p, c_uint32, c_bool, c_double, c_char_p, c_long, c_int, byref

_cf = ctypes.CDLL(ctypes.util.find_library("CoreFoundation"))
_cg = ctypes.CDLL(ctypes.util.find_library("CoreGraphics"))

_cf.CFArrayGetCount.restype = c_long
_cf.CFArrayGetCount.argtypes = [c_void_p]
_cf.CFArrayGetValueAtIndex.restype = c_void_p
_cf.CFArrayGetValueAtIndex.argtypes = [c_void_p, c_long]
_cf.CFDictionaryGetValue.restype = c_void_p
_cf.CFDictionaryGetValue.argtypes = [c_void_p, c_void_p]
_cf.CFStringCreateWithCString.restype = c_void_p
_cf.CFStringCreateWithCString.argtypes = [c_void_p, c_char_p, c_uint32]
_cf.CFStringGetCString.restype = c_bool
_cf.CFStringGetCString.argtypes = [c_void_p, c_char_p, c_long, c_uint32]
_cf.CFNumberGetValue.restype = c_bool
_cf.CFNumberGetValue.argtypes = [c_void_p, c_int, c_void_p]
_cf.CFRelease.argtypes = [c_void_p]
_cg.CGWindowListCopyWindowInfo.restype = c_void_p
_cg.CGWindowListCopyWindowInfo.argtypes = [c_uint32, c_uint32]

_UTF8 = 0x08000100
_DOUBLE = 13  # kCFNumberDoubleType
_ON_SCREEN_ONLY = 1
_EXCLUDE_DESKTOP = 16


def _cfstr(s):
    return _cf.CFStringCreateWithCString(None, s.encode(), _UTF8)


_K = {k: _cfstr(k) for k in ("kCGWindowOwnerName", "kCGWindowBounds",
                             "kCGWindowLayer", "X", "Y", "Width", "Height")}


def _s(p):
    if not p:
        return None
    buf = ctypes.create_string_buffer(512)
    return buf.value.decode() if _cf.CFStringGetCString(p, buf, 512, _UTF8) else None


def _n(p):
    v = c_double(0)
    if p:
        _cf.CFNumberGetValue(p, _DOUBLE, byref(v))
    return v.value


def window_rect(owner_substr):
    """(x, y, w, h) in CoreGraphics coords (top-left origin, y down) of the
    frontmost normal window whose owner name contains owner_substr, else None."""
    info = _cg.CGWindowListCopyWindowInfo(_ON_SCREEN_ONLY | _EXCLUDE_DESKTOP, 0)
    if not info:
        return None
    try:
        sub = owner_substr.lower()
        best, best_area = None, 0.0
        for i in range(_cf.CFArrayGetCount(info)):
            w = _cf.CFArrayGetValueAtIndex(info, i)
            owner = _s(_cf.CFDictionaryGetValue(w, _K["kCGWindowOwnerName"]))
            if not owner or sub not in owner.lower():
                continue
            if int(_n(_cf.CFDictionaryGetValue(w, _K["kCGWindowLayer"]))) != 0:
                continue  # skip menus/panels; 0 == normal window
            b = _cf.CFDictionaryGetValue(w, _K["kCGWindowBounds"])
            if not b:
                continue
            x = _n(_cf.CFDictionaryGetValue(b, _K["X"]))
            y = _n(_cf.CFDictionaryGetValue(b, _K["Y"]))
            wd = _n(_cf.CFDictionaryGetValue(b, _K["Width"]))
            ht = _n(_cf.CFDictionaryGetValue(b, _K["Height"]))
            if wd < 200 or ht < 120:
                continue  # skip small helper windows
            if wd * ht > best_area:  # prefer the largest matching window (the main one)
                best, best_area = (x, y, wd, ht), wd * ht
        return best
    finally:
        _cf.CFRelease(info)


def active_window_rect(owner_substr):
    """Rect of owner's largest window, but ONLY when owner owns the TOPMOST
    normal (layer-0) window on the current Space — i.e. the app is in front.

    Determined entirely from the window stack, so it is immune to our own
    overlay panel (which lives above layer 0 and is ignored here). This avoids
    the feedback loop you get from NSWorkspace.frontmostApplication(), which our
    panel pollutes the moment it's shown."""
    info = _cg.CGWindowListCopyWindowInfo(_ON_SCREEN_ONLY | _EXCLUDE_DESKTOP, 0)
    if not info:
        return None
    try:
        sub = owner_substr.lower()
        top_owner = None          # owner of the frontmost normal window
        best, best_area = None, 0.0
        for i in range(_cf.CFArrayGetCount(info)):
            w = _cf.CFArrayGetValueAtIndex(info, i)
            if int(_n(_cf.CFDictionaryGetValue(w, _K["kCGWindowLayer"]))) != 0:
                continue
            owner = _s(_cf.CFDictionaryGetValue(w, _K["kCGWindowOwnerName"])) or ""
            if top_owner is None:
                top_owner = owner
            b = _cf.CFDictionaryGetValue(w, _K["kCGWindowBounds"])
            if not b:
                continue
            wd = _n(_cf.CFDictionaryGetValue(b, _K["Width"]))
            ht = _n(_cf.CFDictionaryGetValue(b, _K["Height"]))
            if wd < 200 or ht < 120:
                continue
            if sub in owner.lower() and wd * ht > best_area:
                x = _n(_cf.CFDictionaryGetValue(b, _K["X"]))
                y = _n(_cf.CFDictionaryGetValue(b, _K["Y"]))
                best, best_area = (x, y, wd, ht), wd * ht
        return best if (top_owner is not None and sub in top_owner.lower()) else None
    finally:
        _cf.CFRelease(info)


if __name__ == "__main__":
    for name in ("Claude", "Codex"):
        print(name, "-> rect", window_rect(name), "| active", active_window_rect(name))
