#!/usr/bin/env bash
# Operator-only aarch64 port layer for cocos2d-x v4 prebuilt externals (which ship x86-64 only).
# Builds pinned upstream versions as static PIC libs into deps-aarch64/.
set -euo pipefail
R=$(cd "$(dirname "$0")" && pwd)
S=$R/deps-src
O=$R/deps-aarch64
mkdir -p "$O/lib" "$O/build"
J=4
common=(-G Ninja -DCMAKE_BUILD_TYPE=Release -DCMAKE_POSITION_INDEPENDENT_CODE=ON -DCMAKE_INSTALL_PREFIX="$O")

# glfw 3.3.0 (matches external/glfw3/include GLFW_VERSION 3.3.0), static, X11
cmake -S "$S/glfw-3.3" -B "$O/build/glfw" "${common[@]}" -DBUILD_SHARED_LIBS=OFF \
  -DGLFW_BUILD_EXAMPLES=OFF -DGLFW_BUILD_TESTS=OFF -DGLFW_BUILD_DOCS=OFF
ninja -C "$O/build/glfw" -j$J && ninja -C "$O/build/glfw" install

# libuv 1.23.2 (matches external/uv/include)
cmake -S "$S/libuv-1.23.2" -B "$O/build/uv" "${common[@]}" -DCMAKE_C_FLAGS="-Wno-error"
ninja -C "$O/build/uv" -j$J uv_a
cp "$O/build/uv/libuv_a.a" "$O/lib/libuv_a.a"

# libwebsockets 2.4.2 (cocos WebSocket only; game does not use networking)
cmake -S "$S/libwebsockets-2.4.2" -B "$O/build/lws" "${common[@]}" \
  -DLWS_WITH_SHARED=OFF -DLWS_WITH_STATIC=ON -DLWS_WITH_SSL=ON -DLWS_WITHOUT_TESTAPPS=ON \
  -DLWS_WITHOUT_TEST_SERVER=ON -DLWS_WITHOUT_TEST_CLIENT=ON -DLWS_WITH_LIBUV=OFF \
  -DLWS_IPV6=OFF -DCMAKE_C_FLAGS="-Wno-error -Wno-deprecated-declarations"
ninja -C "$O/build/lws" -j$J websockets
cp "$O/build/lws/lib/libwebsockets.a" "$O/lib/libwebsockets.a"

# freetype 2.5.5 (matches external/freetype2/include)
( cd "$S/freetype-2.5.5" && ./configure --prefix="$O" --enable-static --disable-shared \
    --with-pic --without-png --without-harfbuzz --without-bzip2 --without-zlib >/dev/null \
  && make -j$J >/dev/null && make install >/dev/null )

ls -la "$O/lib"
