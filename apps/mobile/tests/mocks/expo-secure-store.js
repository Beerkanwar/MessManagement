const store = new Map();

module.exports = {
  WHEN_UNLOCKED_THIS_DEVICE_ONLY: 1,
  getItemAsync: async (k) => store.get(k) ?? null,
  setItemAsync: async (k, v) => {
    store.set(k, v);
  },
  deleteItemAsync: async (k) => {
    store.delete(k);
  },
  _clear: () => store.clear(),
};
