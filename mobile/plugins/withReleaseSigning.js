const { withAppBuildGradle } = require("@expo/config-plugins");

module.exports = function withReleaseSigning(config) {
  return withAppBuildGradle(config, (config) => {
    let contents = config.modResults.contents;
    if (!contents.includes("signingConfigs {")) {
      contents = contents.replace(
        /android\s*\{/,
        `android {
      signingConfigs {
          release {
              storeFile file(System.getProperty("user.home") + "/.android/debug.keystore")
              storePassword "android"
              keyAlias "androiddebugkey"
              keyPassword "android"
          }
      }`
      );
    }
    if (!contents.includes("signingConfig signingConfigs.release")) {
      contents = contents.replace(
        /buildTypes\s*\{[\s\S]*?release\s*\{/,
        (match) => match + "\n            signingConfig signingConfigs.release"
      );
    }
    return config;
  });
};
