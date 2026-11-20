import { animalSearchText, matchesAnimalTag } from './animalSearch';

const animal = { tag_number: 'MAIN-1', registry_tag_id: 'LEGACY-1', name: 'Bella',
  search_tags: ['901020000131504', 'UHF-1', 'READER-1', 'VISUAL-1', 'BRAND-1', 'OTHER-1'] };

test.each(['MAIN-1', 'LEGACY-1', ...animal.search_tags])('searches and resolves %s', (tag) => {
  expect(animalSearchText(animal).toLowerCase()).toContain(tag.toLowerCase());
  expect(matchesAnimalTag(animal, `  ${tag.toLowerCase()}  `)).toBe(true);
});

test('exact tag resolution excludes names, partial tags and blank input', () => {
  for (const value of ['Bella', 'MAIN', '']) expect(matchesAnimalTag(animal, value)).toBe(false);
  expect(animalSearchText({ tag_number: 'OLD' })).toBe('OLD ');
});
