# Reference analysis (30 fps)

Numbers only, measured with `refscan.py` and `camscan.py` from the user's two reference shorts (no frames, stories or text are stored or copied). These numbers drive the camera grammar, framing and palette rules in SKILL.md.

# Reference A (night camp story)  (1772 frames @ 30 fps, 59.1 s)

**Cuts:** 2 at 19.6s, 39.1s -> average shot 19.7 s

**Camera move mix (share of frames):** creep 22%, orbit/truck 19%, dolly-in 14%, crane 14%, static 12%, dolly-out 12%, pan 2%, tilt 2%, roll 2%, push 1%, pull 0%, shake 0%, cut 0%, start 0%

**Move segments >= 4 f:** 81 (one every 22 frames); median length 8 f; mean speed 0.49 % of frame width per frame; mean parallax 0.91 px/f

**Shot sizes (share of frames, by the biggest white head):** MCU 33%, none 24%, MS 20%, FS 11%, WS 6%, CU 5%, ECU 2%

**Head placement:** top of head at 36% of frame height (p25-p75 29-42%), x centre 52% (p25-p75 35-64%)

**Horizon row:** median 43% of frame height (p25-p75 36-48%)

**Colour (every 0.5 s):** luminance p5/p50/p95 = 36 / 66 / 161; saturation 96/255; warm-cool (R-B) +1; haze ratio 0.61

## Shots
| # | time | s | moves | sizes | speed px/f | parallax | main segments |
|---|---|---|---|---|---|---|---|
| 1 | 0.0-19.6 | 19.63 | dolly-out 25%, orbit/truck 18%, creep 15%, crane 13% | MCU 42%, MS 28%, none 14% | 1.13 | 1.05 | orbit/truck@0.0s/12f; orbit/truck@1.4s/9f; crane@1.7s/20f; crane@2.8s/13f; orbit/truck@4.0s/10f; crane@4.3s/13f; dolly-out@5.8s/19f; dolly-out@6.6s/17f; dolly-out@9.0s/11f; dolly-out@9.4s/13f; dolly-out@13.1s/38f; orbit/truck@15.0s/18f; dolly-out@15.9s/6f; dolly-out@16.1s/10f; dolly-out@16.7s/8f; or |
| 2 | 19.6-39.1 | 19.47 | creep 31%, static 17%, dolly-in 14%, crane 14% | MCU 41%, MS 22%, FS 17% | 0.55 | 0.59 | dolly-in@20.2s/8f; orbit/truck@20.5s/12f; orbit/truck@22.5s/10f; crane@23.4s/9f; orbit/truck@26.2s/18f; orbit/truck@27.4s/18f; crane@30.6s/16f; dolly-in@31.1s/7f; dolly-in@32.4s/8f; crane@33.1s/15f; crane@34.8s/15f; dolly-in@35.7s/10f; dolly-out@36.2s/6f; dolly-in@37.7s/35f |
| 3 | 39.1-59.1 | 19.97 | orbit/truck 24%, creep 19%, dolly-in 18%, crane 15% | none 54%, MCU 17%, MS 10% | 0.99 | 1.08 | orbit/truck@39.8s/16f; dolly-in@40.4s/7f; orbit/truck@41.2s/9f; crane@41.5s/25f; crane@44.9s/8f; orbit/truck@45.1s/61f; dolly-in@47.2s/11f; orbit/truck@47.5s/20f; orbit/truck@49.7s/8f; dolly-in@51.5s/17f; crane@52.8s/10f; dolly-out@53.5s/10f; crane@56.0s/12f; dolly-in@56.4s/11f; dolly-in@58.0s/31f |

## Colour samples (every 2 s)
| t | sky | ground | palette (share) | p50 | sat | warm | haze |
|---|---|---|---|---|---|---|---|
| 0s | #2d3346 | #5f4c3e | #2b3242(0.57) #6f4e3a(0.24) #53677d(0.11) #a57a4a(0.05) #f0f1e0(0.03) | 62 | 99 | -0 | 0.46 |
| 2s | #1f2840 | #3b363c | #24293b(0.66) #414253(0.2) #505a75(0.09) #95715e(0.03) #e5e0d9(0.02) | 47 | 88 | -20 | 0.31 |
| 4s | #212a42 | #4f3d37 | #222c44(0.4) #402f2e(0.33) #495269(0.19) #a06f4b(0.04) #eee7d8(0.03) | 52 | 99 | -10 | 0.23 |
| 6s | #262f46 | #38393d | #282c37(0.37) #303749(0.3) #434958(0.19) #556283(0.13) #ebeae6(0.02) | 55 | 74 | -23 | 0.62 |
| 8s | #272f46 | #665753 | #262d42(0.33) #71615b(0.28) #48444b(0.26) #91978a(0.09) #f5f3f2(0.05) | 72 | 77 | -3 | 0.96 |
| 10s | #927469 | #744340 | #876b65(0.44) #782d2a(0.22) #443942(0.21) #a3948f(0.1) #f9f4e9(0.03) | 97 | 93 | +35 | 0.39 |
| 12s | #927469 | #744441 | #987d72(0.35) #6f5a62(0.23) #7b302b(0.23) #3f323a(0.17) #efece8(0.03) | 97 | 92 | +35 | 0.39 |
| 14s | #796465 | #633732 | #332c2f(0.3) #9e8679(0.24) #685960(0.21) #83251f(0.19) #f7f0e6(0.06) | 79 | 102 | +32 | 0.46 |
| 16s | #786569 | #78443e | #6d5966(0.36) #7c302b(0.2) #a57e6d(0.2) #3d3039(0.18) #e5dcd1(0.06) | 92 | 90 | +32 | 0.36 |
| 18s | #695a64 | #845344 | #615464(0.37) #503134(0.23) #9b583c(0.19) #88818f(0.15) #d3b28d(0.06) | 89 | 91 | +27 | 0.43 |
| 20s | #293149 | #4f3b35 | #2c252d(0.46) #384057(0.31) #706065(0.16) #c39972(0.05) #f1e4d5(0.02) | 53 | 93 | -4 | 0.34 |
| 22s | #2f3750 | #5b3e31 | #353d54(0.47) #4a2e23(0.31) #606985(0.13) #a6724c(0.06) #efe2d5(0.03) | 63 | 107 | -1 | 0.32 |
| 24s | #2e3851 | #69422a | #32394f(0.48) #623923(0.29) #5c6886(0.1) #b16f36(0.09) #ede0d5(0.03) | 65 | 119 | +12 | 0.51 |
| 26s | #2e3750 | #6c422a | #32394f(0.46) #653b23(0.3) #5c6987(0.1) #ab6a36(0.1) #ede2d6(0.04) | 66 | 121 | +15 | 0.84 |
| 28s | #303852 | #76482b | #343a52(0.44) #523122(0.23) #a7622d(0.17) #55607e(0.1) #f1dac3(0.05) | 66 | 119 | +17 | 0.51 |
| 30s | #323a53 | #724629 | #353b53(0.43) #512f21(0.24) #a4612d(0.16) #576282(0.12) #f0dbc8(0.05) | 66 | 118 | +15 | 0.44 |
| 32s | #2d344c | #6b4735 | #2b334b(0.36) #43291f(0.23) #4a546e(0.18) #925730(0.16) #f5e2c4(0.08) | 62 | 116 | +10 | 0.21 |
| 34s | #2a314a | #463a3d | #29252f(0.38) #2b344c(0.32) #4d5671(0.18) #603e32(0.07) #f5e4db(0.05) | 49 | 94 | -15 | 0.25 |
| 36s | #303a55 | #392d2d | #393d51(0.45) #2b2225(0.35) #596788(0.15) #c08f5e(0.03) #f2e7d8(0.02) | 58 | 88 | -12 | 0.62 |
| 38s | #363f58 | #54443e | #363d52(0.35) #352422(0.34) #5d6983(0.15) #f4e3d2(0.11) #bc8252(0.05) | 60 | 95 | +0 | 0.44 |
| 40s | #2d364e | #3b2a29 | #282229(0.44) #3d3d4c(0.4) #62657b(0.08) #e5d9ce(0.05) #aa4f31(0.03) | 54 | 88 | -4 | 0.68 |
| 42s | #414559 | #3a2826 | #484048(0.34) #311f1e(0.3) #21293e(0.21) #736a76(0.08) #e4d6ca(0.06) | 53 | 88 | +1 | 1.29 |
| 44s | #535362 | #544f55 | #2e2c37(0.46) #4e4853(0.3) #786f76(0.12) #edeae8(0.06) #aeabaf(0.05) | 64 | 59 | -5 | 1.14 |
| 46s | #1e263d | #322f39 | #1d263d(0.37) #2d242a(0.28) #353e57(0.26) #515f81(0.08) #af7b4c(0.01) | 43 | 101 | -22 | 0.60 |
| 48s | #232b43 | #2d2b34 | #1c273f(0.33) #252027(0.27) #2c364a(0.23) #3e475d(0.13) #556080(0.04) | 41 | 100 | -24 | 0.82 |
| 50s | #22283e | #2d2d39 | #1f2232(0.52) #252f45(0.37) #434c64(0.1) #b88256(0.01) #f5e6cd(0.0) | 40 | 106 | -24 | 1.26 |
| 52s | #252d45 | #433435 | #212b40(0.42) #23202c(0.23) #384054(0.2) #61321d(0.08) #d99654(0.06) | 44 | 111 | -7 | 0.38 |
| 54s | #6b80a9 | #382f32 | #312425(0.28) #363b46(0.23) #555660(0.21) #647aa6(0.18) #8c9fc3(0.09) | 71 | 66 | -19 | 2.14 |
| 56s | #6178a5 | #413c42 | #312e37(0.38) #7d92bb(0.26) #5c73a0(0.22) #605a59(0.12) #eee8e9(0.01) | 100 | 72 | -32 | 0.39 |
| 58s | #8c8c99 | #8a7a68 | #a19ea2(0.28) #86766d(0.22) #5c5047(0.22) #e8ddc1(0.15) #ecbd7a(0.12) | 146 | 56 | +30 | 0.46 |

# Reference B (day road story)  (1783 frames @ 30 fps, 59.4 s)

**Cuts:** 7 at 27.2s, 31.3s, 35.6s, 37.4s, 51.7s, 54.6s, 58.5s -> average shot 7.4 s

**Camera move mix (share of frames):** creep 26%, dolly-in 23%, orbit/truck 13%, dolly-out 11%, crane 6%, static 6%, roll 3%, tilt 3%, push 3%, whip 3%, pan 2%, pull 1%, cut 0%, shake 0%, start 0%

**Move segments >= 4 f:** 85 (one every 21 frames); median length 6 f; mean speed 0.91 % of frame width per frame; mean parallax 1.20 px/f

**Shot sizes (share of frames, by the biggest white head):** none 63%, FS 14%, WS 12%, MS 8%, MCU 2%, CU 1%, ECU 0%

**Head placement:** top of head at 46% of frame height (p25-p75 41-51%), x centre 52% (p25-p75 38-74%)

**Horizon row:** median 44% of frame height (p25-p75 35-54%)

**Colour (every 0.5 s):** luminance p5/p50/p95 = 44 / 109 / 194; saturation 72/255; warm-cool (R-B) +6; haze ratio 0.68

## Shots
| # | time | s | moves | sizes | speed px/f | parallax | main segments |
|---|---|---|---|---|---|---|---|
| 1 | 0.0-27.2 | 27.17 | creep 27%, dolly-in 19%, dolly-out 16%, orbit/truck 11% | none 53%, FS 18%, WS 17% | 2.04 | 1.26 | dolly-in@0.3s/8f; roll@0.6s/6f; dolly-out@1.2s/17f; whip@3.6s/6f; dolly-in@3.8s/10f; push@4.6s/10f; dolly-out@5.8s/8f; dolly-in@7.7s/18f; crane@8.3s/8f; dolly-out@9.6s/6f; whip@9.8s/10f; dolly-out@10.1s/7f; whip@11.0s/10f; dolly-in@11.3s/6f; dolly-in@13.9s/6f; dolly-out@15.8s/8f; orbit/truck@16.2s/7 |
| 2 | 27.2-31.3 | 4.1 | dolly-in 43%, dolly-out 19%, creep 9%, push 7% | none 56%, MS 20%, FS 10% | 1.95 | 0.89 | push@28.0s/7f; dolly-in@28.3s/12f; dolly-in@28.7s/24f; dolly-out@29.7s/21f; dolly-in@30.5s/10f |
| 3 | 31.3-35.6 | 4.37 | dolly-in 56%, orbit/truck 8%, crane 8%, dolly-out 8% | none 60%, FS 19%, WS 11% | 2.17 | 1.67 | dolly-in@31.3s/10f; dolly-in@32.5s/22f; dolly-in@33.4s/31f |
| 4 | 35.6-37.4 | 1.77 | creep 67%, static 8%, orbit/truck 8%, crane 8% | FS 72%, MS 21%, WS 8% | 0.38 | 0.42 |  |
| 5 | 37.4-51.7 | 14.33 | creep 26%, dolly-in 22%, orbit/truck 18%, crane 9% | none 87%, MCU 4%, WS 3% | 1.42 | 1.49 | dolly-out@37.9s/12f; orbit/truck@38.3s/14f; orbit/truck@39.2s/12f; dolly-in@39.9s/8f; dolly-in@40.2s/6f; orbit/truck@42.3s/6f; orbit/truck@42.5s/6f; whip@43.1s/7f; tilt@44.3s/15f; dolly-in@45.8s/11f; dolly-in@46.5s/11f; crane@47.4s/6f; dolly-in@47.7s/8f; dolly-in@49.2s/17f |
| 6 | 51.7-54.6 | 2.87 | static 44%, dolly-in 26%, creep 20%, orbit/truck 5% | none 48%, WS 40%, FS 12% | 0.56 | 0.53 | dolly-in@52.2s/22f |
| 7 | 54.6-58.5 | 3.87 | creep 44%, orbit/truck 32%, dolly-in 10%, static 4% | none 97%, WS 2%, FS 1% | 0.56 | 0.61 | orbit/truck@56.5s/19f |
| 8 | 58.5-59.4 | 0.97 | creep 39%, static 36%, crane 11%, dolly-out 4% | none 100% | 0.26 | 0.28 |  |

## Colour samples (every 2 s)
| t | sky | ground | palette (share) | p50 | sat | warm | haze |
|---|---|---|---|---|---|---|---|
| 0s | #bbbec6 | #4a6733 | #3d582b(0.3) #d4d5d6(0.24) #65854b(0.21) #b2b6c0(0.17) #90907a(0.08) | 139 | 73 | +9 | 0.37 |
| 2s | #617466 | #828778 | #384427(0.42) #686f55(0.21) #969f69(0.15) #c7cccf(0.13) #7b9ac5(0.09) | 105 | 92 | +10 | 0.69 |
| 4s | #404934 | #709140 | #2f3729(0.33) #5d8728(0.26) #d1d3d4(0.21) #aab86d(0.11) #6e7b61(0.1) | 116 | 91 | +23 | 0.86 |
| 6s | #9cb1d0 | #5f6248 | #c8ccd6(0.33) #424c3b(0.28) #7fa1ce(0.17) #8f8860(0.12) #bfaf71(0.1) | 158 | 70 | -2 | 0.48 |
| 8s | #a0b3d1 | #6e7254 | #c9cdd6(0.38) #4d5b3b(0.2) #797966(0.18) #87a6d0(0.16) #b1a56d(0.08) | 163 | 59 | -4 | 0.40 |
| 10s | #354437 | #828684 | #232b21(0.37) #7b7e87(0.28) #8fafd0(0.16) #525d45(0.13) #a0a74c(0.05) | 109 | 70 | -7 | 0.70 |
| 12s | #566061 | #8b8a81 | #828083(0.34) #bdc8d7(0.29) #273027(0.14) #5b574c(0.12) #cfaf7d(0.11) | 132 | 48 | +3 | 1.36 |
| 14s | #535653 | #b19c7d | #8a7b60(0.31) #d19d70(0.23) #353527(0.22) #e1d2c5(0.15) #859fc6(0.08) | 137 | 85 | +38 | 1.05 |
| 16s | #272624 | #443931 | #23211f(0.48) #5e4d43(0.21) #3d312b(0.2) #9e795e(0.09) #ebbc8f(0.02) | 44 | 63 | +19 | 0.53 |
| 18s | #556362 | #b29874 | #8f8b60(0.33) #323c26(0.24) #e3d9d0(0.2) #8ca1bf(0.16) #f67365(0.07) | 140 | 80 | +24 | 1.12 |
| 20s | #686b61 | #837467 | #3a3b2e(0.26) #74695a(0.25) #cdcbce(0.22) #b88a71(0.21) #8493a2(0.06) | 123 | 68 | +23 | 1.19 |
| 22s | #53757c | #404f49 | #293630(0.3) #445a49(0.26) #76a3d3(0.24) #5477a1(0.11) #b39668(0.08) | 90 | 99 | -28 | 0.89 |
| 24s | #6996cb | #a39f99 | #669bd4(0.38) #9f9fa3(0.33) #bfc9d4(0.14) #545b67(0.12) #ddb05c(0.04) | 156 | 73 | -43 | 0.32 |
| 26s | #8b97a4 | #636e63 | #343e33(0.36) #dddbd1(0.22) #706355(0.2) #97b0c6(0.13) #a09c7e(0.09) | 110 | 64 | +6 | 0.66 |
| 28s | #5e6e2f | #908b5d | #26301e(0.37) #a0ad36(0.22) #a28e7d(0.18) #656c3c(0.14) #9cb0cb(0.09) | 124 | 111 | +35 | 0.83 |
| 30s | #584e40 | #6e605c | #66564d(0.37) #312d23(0.26) #9c928d(0.23) #ebd3c6(0.07) #e1534d(0.06) | 90 | 69 | +28 | 0.94 |
| 32s | #484339 | #5b453a | #2d281b(0.33) #746770(0.28) #534434(0.27) #dcc1be(0.07) #c6212b(0.05) | 71 | 90 | +25 | 0.72 |
| 34s | #7bb1e3 | #949571 | #a3c8ee(0.38) #7ab0e1(0.25) #98927f(0.15) #c1cb74(0.13) #3f3d33(0.09) | 181 | 87 | -39 | 0.56 |
| 36s | #4b4140 | #8d7c74 | #6b5e59(0.3) #846f69(0.25) #34302f(0.24) #f0e0ce(0.11) #a89688(0.1) | 105 | 47 | +20 | 0.64 |
| 38s | #a3a3ad | #8a7d6d | #594c48(0.38) #c2a94d(0.17) #c4bcbc(0.16) #8d96ae(0.16) #f7efe1(0.14) | 154 | 65 | +26 | 0.48 |
| 40s | #969fb7 | #635948 | #b5b5c2(0.32) #514746(0.29) #bd9a5c(0.17) #718dbd(0.12) #7c7c38(0.1) | 145 | 71 | +13 | 0.51 |
| 42s | #7795c6 | #8c775d | #64534e(0.25) #7291c2(0.25) #afb6cd(0.22) #ca9b56(0.21) #f1dec8(0.07) | 151 | 83 | +6 | 0.60 |
| 44s | #444f5d | #292a2f | #1a1b1f(0.39) #3e4755(0.22) #586376(0.21) #818894(0.14) #adb1b5(0.04) | 72 | 54 | -16 | 0.47 |
| 46s | #373d4d | #51373e | #353a4a(0.42) #40252d(0.25) #4d5365(0.25) #8d919b(0.05) #ad4738(0.03) | 60 | 80 | -7 | 0.40 |
| 48s | #40475a | #423f47 | #4d5464(0.44) #3c3f50(0.23) #312d36(0.23) #6b6976(0.08) #a39a98(0.02) | 78 | 60 | -16 | 0.53 |
| 50s | #2c3035 | #322f30 | #1a1b1e(0.42) #363838(0.2) #5a5f6b(0.2) #8f8a88(0.12) #beb4af(0.06) | 51 | 45 | -4 | 0.62 |
| 52s | #2f2e3b | #a88763 | #2c2e39(0.31) #473125(0.25) #c7a177(0.15) #e4c18f(0.15) #735544(0.14) | 61 | 94 | +35 | 0.51 |
| 54s | #151214 | #2a211a | #131012(0.49) #282018(0.28) #4f341e(0.12) #f1ce99(0.08) #a07341(0.02) | 26 | 82 | +20 | 0.25 |
| 56s | #313339 | #1c191b | #161518(0.35) #414148(0.3) #2a2625(0.21) #796c62(0.11) #ddab7f(0.03) | 43 | 48 | +4 | 0.54 |
| 58s | #3e3934 | #1b191a | #1a181a(0.45) #3d3836(0.33) #645951(0.13) #a88767(0.06) #eec399(0.03) | 47 | 47 | +11 | 0.58 |