// All active identifier types are supplied by the animal list API.
export const animalTags = (animal) =>
  [animal.tag_number, animal.registry_tag_id, ...(animal.search_tags || [])].filter(Boolean);

export const animalSearchText = (animal) =>
  [...animalTags(animal), animal.name || ''].join(' ');

export const matchesAnimalTag = (animal, query) => {
  const tag = query.trim().toLowerCase();
  return Boolean(tag) && animalTags(animal).some((value) => value.toLowerCase() === tag);
};
