// World layout for the v2 demo ("The Grocer's Rocket Cart"): pure data in metres, shared by world.js and story.js.
// Valley road runs south (+z, village) to north (-z), then climbs the festival hill. Replace for each new story.
export const ROAD = [[0, 170], [0, 100], [1, 40], [3, -10], [9, -60], [19, -110], [26, -150], [30, -190], [31, -215]];
export const ROAD_W = 7;
export const HILL = { x: 31, z: -222, r: 52, h: 19 };
// houses: [x, z, width (along road), depth, wall height, facing yaw, roof kind 0 terracotta / 1 slate, storeys]
export const HOUSES = [
  [-11, 88, 8, 6, 5.6, Math.PI / 2, 0, 1], [-11.5, 74, 7, 6, 6.2, Math.PI / 2, 1, 2], [-11, 60, 9, 6.5, 5.4, Math.PI / 2, 0, 1], [-12, 45, 7.5, 6, 6.4, Math.PI / 2, 1, 2],
  [-11.5, 30, 8, 6, 5.5, Math.PI / 2, 0, 1], [11.5, 92, 7.5, 6, 6, -Math.PI / 2, 1, 2], [11, 78, 8.5, 6.5, 5.4, -Math.PI / 2, 0, 1], [12, 63, 7, 6, 6.3, -Math.PI / 2, 0, 2],
  [11.5, 48, 9, 6, 5.6, -Math.PI / 2, 1, 1], [12.5, 33, 7.5, 6, 6.1, -Math.PI / 2, 0, 2], [-24, 70, 8, 7, 5.5, Math.PI / 2, 0, 1], [25, 58, 8, 7, 5.8, -Math.PI / 2, 1, 1],
];
// street lanterns along the road (warm PointLights at night): [x, z]
export const LANTERNS = [[-5.2, 96], [5.2, 84], [-5.2, 70], [5.2, 56], [-5.2, 42], [5.2, 28], [-5.4, 12], [6.5, -8], [3, -40], [16, -88], [21, -130], [24.5, -175], [27.5, -200]];
export const TREES = [[-20, 104, 1.1], [19, 106, 1.0], [-19, 20, 1.2], [20, 18, 0.9], [-14, 2, 1.0], [16, -20, 1.1], [-8, -34, 1.3], [24, -48, 1.0], [-2, -80, 1.2], [33, -95, 1.1],
  [8, -120, 1.0], [40, -140, 1.2], [14, -165, 0.9], [44, -190, 1.0], [18, -205, 1.1], [45, -235, 0.9], [-30, 40, 1.3], [32, 82, 1.2], [-35, 98, 1.0], [38, 30, 1.1]];
export const PROPS = {
  carts: [[-6.5, 66, 0.3], [7, 40, -0.2]], barrels: [[-7.2, 52], [-7.8, 52.9], [-7.4, 53.8], [7.6, 70.5], [8.2, 71.3]], crates: [[7.8, 86, 0.2], [8.6, 86.6, 0.5], [-7.6, 34, 0.1]],
  fences: [[[-6, 20], [-6, 4]], [[7.5, 8], [10, -30]], [[15, -70], [21, -108]], [[24, -118], [29, -150]]],
  signs: [[5.6, 8, -0.25, "HILL 2 km"]], tents: [[22, -212, 0.6, "#c9452f"], [40, -206, -0.4, "#e8c34a"], [36, -230, 1.2, "#3f7fb5"]],
  vehicles: [[-6.2, 150, 0.2, "#9b1e22"]],
};
/** the rocket cart route: arc length along ROAD where it starts and the hill top target */
export const CART = { s0: 60, top: [30.6, -214] };
