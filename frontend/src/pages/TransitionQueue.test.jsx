import { groupQueue, overdueMonths, overdueTone, ruleLabel, sexForItem } from './TransitionQueue';

jest.mock('../lib/api', () => ({
  getLocations: jest.fn(), getTransitionRules: jest.fn(), getTransitionQueue: jest.fn(), bulkConfirmTransitions: jest.fn(),
}));

const femaleRule = {
  id: 1, species: 'cattle', from_category_name: 'Achishwa Jike', to_category_id_f: 11, to_category_name_f: 'Mitamba',
  to_category_id_m: null, to_category_name_m: null, trigger_type: 'age', trigger_age_months: 18, is_active: true,
};
const maleRule = {
  id: 2, species: 'cattle', from_category_name: 'Achishwa Dume', to_category_id_f: null, to_category_name_f: null,
  to_category_id_m: 12, to_category_name_m: 'Dume Wadogo', trigger_type: 'age', trigger_age_months: 18, is_active: true,
};
const eventRule = { id: 3, species: 'cattle', trigger_type: 'event', is_active: true };
const inactive = { ...maleRule, id: 4, is_active: false };
const sheepRule = { ...femaleRule, id: 5, species: 'sheep' };

test('ruleLabel shows the single sex-specific target, or both when they differ', () => {
  expect(ruleLabel(femaleRule)).toBe('Achishwa Jike → Mitamba');
  expect(ruleLabel({ ...femaleRule, to_category_name_m: 'Maksai' })).toBe('Achishwa Jike → Mitamba / Maksai');
});

test('sex is inferred from which target the item is moving to', () => {
  expect(sexForItem({ to_category_id: 11 }, femaleRule)).toBe('female');
  expect(sexForItem({ to_category_id: 12 }, maleRule)).toBe('male');
  expect(sexForItem({ to_category_id: 11 }, { ...femaleRule, to_category_id_m: 11 })).toBeNull();
  expect(sexForItem({ to_category_id: 99 }, femaleRule)).toBeNull();
  expect(sexForItem({ to_category_id: 11 }, undefined)).toBeNull();
});

test('overdue months and tone bands', () => {
  expect(overdueMonths({ age_months: 21 }, femaleRule)).toBe(3);
  expect(overdueMonths({ age_months: 18 }, femaleRule)).toBe(0);
  expect(overdueMonths({ age_months: 5 }, femaleRule)).toBe(0); // never negative
  expect(overdueMonths({ age_months: 30 }, undefined)).toBe(0);
  expect([0, 1, 2, 3, 9].map(overdueTone)).toEqual(['none', 'amber', 'amber', 'red', 'red']);
});

test('groupQueue makes one group per active age rule, keeps empty ones, and honours the species filter', () => {
  const pending = [{ animal_id: 1, rule_id: 1 }, { animal_id: 2, rule_id: 1 }, { animal_id: 3, rule_id: 2 }];
  const groups = groupQueue([femaleRule, maleRule, eventRule, inactive, sheepRule], pending, null);
  expect(groups.map((g) => [g.rule.id, g.items.length])).toEqual([[1, 2], [2, 1], [5, 0]]);
  expect(groupQueue([femaleRule, sheepRule], pending, 'sheep').map((g) => g.rule.id)).toEqual([5]);
});
