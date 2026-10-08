// Global Jest setup: enable fetch mocking for every test file.
// The API client is the only network boundary, so tests exercise it through
// jest-fetch-mock instead of hitting a real server.
require("jest-fetch-mock").enableMocks();

// AsyncStorage ships a jest mock; zustand's persist middleware uses it.
jest.mock("@react-native-async-storage/async-storage", () =>
  require("@react-native-async-storage/async-storage/jest/async-storage-mock"),
);
