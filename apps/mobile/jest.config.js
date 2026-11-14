/** @type {import('ts-jest').JestConfigWithTsJest} */
module.exports = {
  preset: 'ts-jest',
  testEnvironment: 'node',
  testMatch: ['**/tests/**/*.test.ts', '**/__tests__/**/*.test.ts'],
  moduleFileExtensions: ['ts', 'tsx', 'js', 'jsx', 'json'],
  transform: {
    '^.+\\.tsx?$': [
      'ts-jest',
      {
        tsconfig: 'tsconfig.json',
      },
    ],
  },
  moduleNameMapper: {
    '^react-native$': '<rootDir>/tests/mocks/react-native.js',
    '^expo-secure-store$': '<rootDir>/tests/mocks/expo-secure-store.js',
    '^expo-device$': '<rootDir>/tests/mocks/expo-device.js',
    '^expo-application$': '<rootDir>/tests/mocks/expo-application.js',
    '^expo-crypto$': '<rootDir>/tests/mocks/expo-crypto.js',
    '^expo-screen-capture$': '<rootDir>/tests/mocks/expo-screen-capture.js',
    '^@react-native-community/netinfo$': '<rootDir>/tests/mocks/netinfo.js',
  },
};
