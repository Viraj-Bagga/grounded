# 05-app

Epic 5, the React Native app shell. Not scaffolded yet: blocked on Xcode.

## The llama.rn pin is deliberate

`llama.rn` is pinned to **exactly `0.12.9`**. Not a caret range, not `latest`.

npm's `latest` tag currently resolves to `0.13.0-rc.3`, and there is no stable
0.13.0, so a plain `npm install llama.rn` silently pulls a release candidate.
0.12.9 is the newest stable and it supports the model architecture just as
fully. Verified 2026-09-15 by reading the vendored source and the shipped
binary, not the docs:

- 0.12.9 vendors llama.cpp build 10256, commit 6c8dcaa
- `LLM_ARCH_NEMOTRON_H` is present and mapped to the string `"nemotron_h"`,
  which is what our GGUF declares
- `cpp/models/nemotron-h.cpp` is a real 258-line implementation, and it reads
  all five SSM hparams our file provides
- the prebuilt `ios/rnllama.xcframework` simulator slice is a universal Mach-O
  (x86_64 + arm64) containing the `nemotron_h` string, both Mamba-2 SSM kernels,
  and tensor-name templates `blk.%d.ssm_a` / `ssm_conv1d` / `ssm_dt` matching
  our GGUF exactly

## After `npm install`

The `postinstall` (`download-native-artifacts.js`) fetches the prebuilt Android
JNI libs and the iOS xcframework from the matching GitHub release. npm's
`allowScripts` policy may block it, which is an npm setting and not an llama.rn
problem. If blocked, run it directly:

```
cd node_modules/llama.rn && node ./install/download-native-artifacts.js
```

## Still unproven

Architecture support is settled. Loading is not: `initLlama` has never been
called. The open risk is memory, not architecture. 4B at Q4 is about 3 GB
resident against 4 to 6 GB devices, which is a does-not-run problem. Note that
the iOS simulator borrows Mac RAM, so a clean load there tests the binding and
the architecture path and says nothing about the memory ceiling on a phone.
