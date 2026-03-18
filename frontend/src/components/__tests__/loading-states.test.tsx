import { describe, it, expect, vi, beforeEach } from 'vitest';
import '@testing-library/jest-dom';

vi.mock('../../api', () => ({
  api: {
    getFilters: vi.fn(),
    getSample: vi.fn(),
    getCount: vi.fn(),
    getHistory: vi.fn(),
    getHistoryRun: vi.fn(),
    deleteHistoryRun: vi.fn(),
    generateReport: vi.fn(),
    checkReady: vi.fn(),
    checkHealth: vi.fn(),
  },
  startSurveySSE: vi.fn(),
  startFollowupSSE: vi.fn(),
}));

import { api } from '../../api';

describe('Loading state API', () => {
  it('api.checkReady should be a function', () => {
    expect(typeof api.checkReady).toBe('function');
  });

  it('api.checkHealth should be a function', () => {
    expect(typeof api.checkHealth).toBe('function');
  });
});
