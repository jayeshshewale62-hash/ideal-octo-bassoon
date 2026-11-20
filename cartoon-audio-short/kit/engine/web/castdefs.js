// Outfits for the cast (rural Bihar, 1960-82)
export const MANJHI_Y = { top: "#e9dfc7", short: true, dhoti: "#f3eee2", pagri: "#c9452f", skin: "#b97d52", beard: "#2b201b", beardSize: 0.8, moustache: "#2b201b", barefoot: true };
export const MANJHI_M = { ...MANJHI_Y, beard: "#8d857c", beardSize: 1.1, moustache: "#8d857c", top: "#e2d6bc" };
export const MANJHI_O = { ...MANJHI_Y, beard: "#f2f0ea", beardSize: 1.5, moustache: "#f2f0ea", hairWhite: "#f2f0ea", skin: "#ab7048", top: "#dccfb4", dhoti: "#ece5d4", pagri: "#b7402e" };
export const FALGUNI = { sari: "#d8572e", border: "#efc13c", top: "#8a3460", skin: "#c3875a", hairCol: "#221816", barefoot: true };
export const VIL_1 = { top: "#3f6fb5", kurta: true, dhoti: "#efe8d8", pagri: "#e0b84a", skin: "#c58c5e", moustache: "#2a1f1a", barefoot: true };
export const VIL_2 = { sari: "#3f8f5a", border: "#e8608a", top: "#e0b84a", skin: "#b8794c", hairCol: "#1e1614", barefoot: true };
export const VIL_3 = { top: "#b5653f", kurta: true, dhoti: "#efe8d8", pagri: "#f0ead9", skin: "#a86d44", moustache: "#ece8df", beard: "#ece8df", beardSize: 0.6, barefoot: true };
export const KID = { build: "kid", top: "#f08a2c", short: true, shorts: "#3b5b9a", hair: "#1f1715", skin: "#c08454", barefoot: true };
export const VIL_4 = { top: "#7b5ac9", kurta: true, dhoti: "#efe8d8", hair: "#231a17", skin: "#b0744a", moustache: "#231a17", barefoot: true };
export const VIL_5 = { sari: "#c03a5a", border: "#f1c94a", top: "#3f6fb5", skin: "#c99062", hairCol: "#1e1614", barefoot: true };

// ---- v2.1 reference style: white round heads, solid-black stick limbs, patterned torsos, bold hats ----
const REF = { skin: "#ffffff", stick: true };
export const GROCER = { ...REF, top: "#3fae9a", pattern: "stripes", patCol: "#2a7d6f", patCol2: "#bfeee2", hair: "#0e0c10", hat: "topknot", moustache: null, build: "stout" };
export const MAYOR = { ...REF, top: "#7a2f6e", pattern: "ikat", patCol: "#c0353a", patCol2: "#f1c94a", moustache: "#0e0c10", hat: "kasa", hatCol: "#c0353a", band: "#e8c34a", build: "stout" };
export const TOWN_1 = { ...REF, top: "#c8482f", pattern: "ikat", patCol: "#2a2340", patCol2: "#f4ead8", hat: "brim", hatCol: "#7a5233", band: "#3a2a20" };
export const TOWN_2 = { ...REF, top: "#e0b84a", pattern: "check", patCol: "#a8452f", hair: "#0e0c10" };
export const TOWN_KID = { ...REF, build: "kid", top: "#3f7fb5", pattern: "dots", patCol2: "#f4ead8", hat: "cap", hatCol: "#c0353a" };
