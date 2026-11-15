# libgomp.so.1

GNU OpenMP runtime for Linux x86_64, needed by LightGBM's Linux wheel (`lib_lightgbm.so` links `libgomp.so.1`,
symbols up to `GOMP_4.5`) and missing from the Vercel serverless runtime. `api/index.py` loads it only when the
system has none.

- Source: Debian 11 package `libgomp1_10.2.1-6_amd64.deb` (GCC 10.2.1), file `usr/lib/x86_64-linux-gnu/libgomp.so.1.0.0`
- sha256: `e80b85fef97ff22f2ce71b5438ba6effada3d635498336d836df95647f7325b9`
- Needs glibc 2.17 or newer. Licence: GPL-3.0 with the GCC Runtime Library Exception.
