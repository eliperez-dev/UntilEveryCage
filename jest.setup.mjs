import { jest } from '@jest/globals';

/**
 * Jest setup file for mocking browser globals and Leaflet
 */


// Mock Leaflet library
global.L = {
  icon: jest.fn((options) => ({
    options,
    _getIconUrl: jest.fn(),
  })),
  
  Icon: class MockIcon {
    constructor(options) {
      this.options = options;
    }
  },
  
  DomUtil: {
    create: jest.fn((tag, className) => ({
      tagName: tag,
      className: className || '',
      style: {},
      appendChild: jest.fn(),
      addEventListener: jest.fn(),
    })),
    addClass: jest.fn(),
    removeClass: jest.fn(),
    hasClass: jest.fn(() => false),
  },
  
  DomEvent: {
    on: jest.fn(),
    off: jest.fn(),
    stop: jest.fn(),
  },
  
  Control: {
    extend: jest.fn((obj) => function() { return obj; }),
  },
  
  map: jest.fn(() => ({
    addControl: jest.fn(),
    getContainer: jest.fn(() => ({
      requestFullscreen: jest.fn(),
      webkitRequestFullscreen: jest.fn(),
      mozRequestFullScreen: jest.fn(),
      msRequestFullscreen: jest.fn(),
    })),
    invalidateSize: jest.fn(),
    locate: jest.fn(),
    on: jest.fn(),
    setView: jest.fn(),
  })),
  
  marker: jest.fn(() => ({
    addTo: jest.fn(() => ({
      bindPopup: jest.fn(() => ({
        openPopup: jest.fn(),
      })),
    })),
  })),
};

// Mock DOM elements for testing
global.document = {
  ...global.document,
  getElementById: jest.fn((id) => {
    const element = {
      id,
      value: '',
      textContent: '',
      innerHTML: '',
      style: {},
      classList: {
        add: jest.fn(),
        remove: jest.fn(),
        contains: jest.fn(() => false),
      },
      addEventListener: jest.fn(),
      removeEventListener: jest.fn(),
    };
    return element;
  }),
  
  querySelector: jest.fn((selector) => ({
    textContent: '',
    style: {},
    classList: {
      add: jest.fn(),
      remove: jest.fn(),
      contains: jest.fn(() => false),
    },
  })),
  
  createElement: jest.fn((tag) => ({
    tagName: tag,
    textContent: '',
    value: '',
    appendChild: jest.fn(),
    style: {},
    classList: {
      add: jest.fn(),
      remove: jest.fn(),
    },
  })),
  
  fullscreenElement: null,
  exitFullscreen: jest.fn(),
  webkitExitFullscreen: jest.fn(),
  mozCancelFullScreen: jest.fn(),
  msExitFullscreen: jest.fn(),
};

// Mock window object
global.window = {
  ...global.window,
  alert: jest.fn(),
  confirm: jest.fn(() => true),
  location: {
    href: 'http://localhost/',
    origin: 'http://localhost',
    search: '',
    hash: '',
  },
};

// Mock console methods to reduce noise in tests
global.console = {
  ...global.console,
  log: jest.fn(),
  warn: jest.fn(),
  error: jest.fn(),
};


