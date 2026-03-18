import { describe, it, expect, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
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
    checkReady: vi.fn().mockResolvedValue(true),
    checkHealth: vi.fn().mockResolvedValue({ mock_llm: true, llm_reachable: true }),
  },
  startSurveySSE: vi.fn(),
  startFollowupSSE: vi.fn(),
}));

describe('SurveyConfig', () => {
  it('should show LLM warning when llmStatus indicates unreachable', async () => {
    // Import dynamically after mocks are set up
    const { useStore } = await import('../../store');

    // Set store state to simulate LLM unreachable
    useStore.setState({
      surveyTheme: 'テスト',
      questions: ['質問1'],
      selectedPersonas: [{ uuid: 'p1', name: 'テスト', age: 30, sex: '男',
        prefecture: '東京都', region: '関東', occupation: '会社員',
        education_level: '大学卒', marital_status: '未婚', persona: 'テスト',
        professional_persona: '', cultural_background: '', skills_and_expertise: '',
        hobbies_and_interests: '', career_goals_and_ambitions: '' }],
      surveyLabel: '',
      llmStatus: { mock_llm: false, llm_reachable: false },
    });

    const SurveyConfig = (await import('../SurveyConfig')).default;
    render(<SurveyConfig />);

    // Should show a warning about LLM being unreachable
    expect(screen.getByText(/LLM.*接続できません/)).toBeInTheDocument();
  });
});
