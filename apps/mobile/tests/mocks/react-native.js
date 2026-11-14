module.exports = {
  Platform: {
    OS: 'android',
    select: (objs) => (objs && objs.android !== undefined ? objs.android : objs ? objs.default : undefined),
  },
  BackHandler: {
    addEventListener: () => ({ remove: () => {} }),
  },
  StyleSheet: {
    create: (styles) => styles,
  },
  Share: {
    share: async () => ({ action: 'sharedAction' }),
  },
};
