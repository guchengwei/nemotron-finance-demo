import type { FiltersResponse, Persona } from '../../src/types'

export const filtersFixture: FiltersResponse = {
  sex: ['男', '女'],
  age_ranges: ['20-29', '30-39'],
  regions: ['関東'],
  prefectures: ['東京都'],
  occupations_top50: ['会社員'],
  education_levels: ['大学卒'],
  financial_literacy: ['初心者', '中級者'],
  total_count: 100,
}

export const samplePersona: Persona = {
  uuid: 'persona-1',
  name: '田中太郎',
  age: 35,
  sex: '男',
  prefecture: '東京都',
  region: '関東',
  occupation: '会社員',
  education_level: '大学卒',
  marital_status: '既婚',
  persona: 'テスト用ペルソナ',
  professional_persona: '会社員',
  cultural_background: '日本',
  skills_and_expertise: '営業',
  hobbies_and_interests: '読書',
  career_goals_and_ambitions: '昇進',
}
