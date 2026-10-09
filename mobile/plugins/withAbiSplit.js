const { withAppBuildGradle } = require("@expo/config-plugins");

module.exports = function withAbiSplit(config) {
  return withAppBuildGradle(config, (config) => {
    const splitBlock = `
      splits {
          abi {
              enable true
              reset()
              include "arm64-v8a"
              universalApk false
          }
      }
      `;
    // Insert the splits block inside the android { } section if it
    // is not already present.
    if (!config.modResults.contents.includes("splits {")) {
      config.modResults.contents = config.modResults.contents.replace(
        /android\s*\{/,
        `android {${splitBlock}`
      );
    }
    return config;
  });
};
