export default {
  // Test environment for DOM testing
  testEnvironment: 'jsdom',
  
  // Support native ES modules through Node/Jest's ESM mode.
  transform: {},
  
  // Test file patterns
  testMatch: [
    '**/__tests__/**/*.js',
    '**/*.test.js',
    '**/*.spec.js'
  ],
  
  // Coverage settings
  collectCoverageFrom: [
    'static/modules/**/*.js',
    '!static/modules/**/*.test.js',
    '!static/modules/**/*.spec.js'
  ],
  
  // Setup files
  setupFilesAfterEnv: ['<rootDir>/jest.setup.mjs'],
  
  // Module paths
  roots: ['<rootDir>'],
  moduleDirectories: ['node_modules', '<rootDir>'],
  
  // Verbose output
  verbose: true
};
