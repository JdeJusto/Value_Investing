// Global Jest setup: enable fetch mocking for every test file.
// The API client is the only network boundary, so tests exercise it through
// jest-fetch-mock instead of hitting a real server.
require("jest-fetch-mock").enableMocks();
