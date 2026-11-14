module.exports = {
  addEventListener: () => () => {},
  fetch: async () => ({
    isConnected: true,
    isInternetReachable: true,
    type: 'wifi',
  }),
};
