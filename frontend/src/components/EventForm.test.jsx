import { applyEventChange, blankEvent, eventFromApi, eventToCreatePayload, eventToUpdatePayload, validateEvent } from './EventForm';

jest.mock('../lib/api', () => ({ searchAnimals: jest.fn() }));

test.each(['gift_in', 'gift_out'])('preserves new %s details in the API payload', (event_type) => {
  const payload = eventToCreatePayload({ ...blankEvent(), event_type,
    gift_party_name: 'Asha', gift_party_phone: '123', gift_reason: 'Breeding' });
  expect(payload).toMatchObject({ gift_party_name: 'Asha', gift_party_phone: '123', gift_reason: 'Breeding' });
});

test('changing a death to a birth removes the structured death cause from creation', () => {
  const event = { ...blankEvent(), event_type: 'death', cause_of_death_id: '4', cause_of_death: 'Disease', disease_id: '2' };
  const payload = eventToCreatePayload(applyEventChange(event, 'event_type', 'birth'));
  expect(payload).toMatchObject({ event_type: 'birth', cause_of_death_id: null, cause_of_death: null, disease_id: null });
});

test('editing mixed tagged and untagged offspring preserves their positions', () => {
  const form = eventFromApi({ event_type: 'birth', species: 'cattle', count: 3, offspring_tags: 'A, , B' });
  expect(eventToUpdatePayload(form).offspring_tags).toBe('A, , B');
});

test('a sale changed to abortion excludes sale fields and disables stock', () => {
  const form = applyEventChange({ ...blankEvent(), event_type: 'sold', buyer_name: 'Asha', sale_price: '100' }, 'event_type', 'abortion');
  expect(eventToCreatePayload(form)).toMatchObject({ is_stock_event: false, buyer_name: null, sale_price: null });
  expect(eventToUpdatePayload(form)).not.toHaveProperty('buyer_name');
});

test('an auto-filled category is released when event type or species changes, but a manual one is kept', () => {
  const auto = { ...blankEvent(), event_type: 'sold', category_id: '7', category_auto_filled: true };
  expect(applyEventChange(auto, 'species', 'goat')).toMatchObject({ category_id: '', category_auto_filled: false });
  expect(applyEventChange(auto, 'event_type', 'death')).toMatchObject({ category_id: '', category_auto_filled: false });
  const manual = { ...blankEvent(), event_type: 'sold', category_id: '7' };
  expect(applyEventChange(manual, 'event_type', 'death').category_id).toBe('7');
});

test('overriding the category by hand clears the auto-filled flag and it never reaches the payload', () => {
  const auto = { ...blankEvent(), event_type: 'sold', category_id: '7', category_auto_filled: true };
  const next = applyEventChange(auto, 'category_id', '9');
  expect(next).toMatchObject({ category_id: '9', category_auto_filled: false });
  expect(eventToCreatePayload(auto)).not.toHaveProperty('category_auto_filled');
  expect(eventToUpdatePayload(auto)).not.toHaveProperty('category_auto_filled');
});


test('PD and service payloads are non-stock and do not require a category', () => {
  const pd = { ...applyEventChange(blankEvent(), 'event_type', 'pd_test'), pd_result: 'pregnant', months_pregnant: '0' };
  expect(validateEvent(pd)).toBeNull();
  expect(eventToCreatePayload(pd)).toMatchObject({ is_stock_event: false, pd_result: 'pregnant', months_pregnant: 0 });
  expect(eventToUpdatePayload(pd)).toMatchObject({ pd_result: 'pregnant', months_pregnant: 0 });
  const open = applyEventChange(pd, 'pd_result', 'open');
  expect(eventToUpdatePayload(open).months_pregnant).toBeNull();
  const service = applyEventChange(pd, 'event_type', 'service');
  expect(validateEvent(service)).toBeNull();
  expect(eventToCreatePayload(service)).toMatchObject({ is_stock_event: false, pd_result: null, months_pregnant: null });
});

test('PD result is required and rejects invalid pregnancy months', () => {
  const pd = applyEventChange(blankEvent(), 'event_type', 'pd_test');
  expect(validateEvent(pd)).toContain('PD result');
  expect(validateEvent({ ...pd, pd_result: 'pregnant', months_pregnant: '-1' })).toContain('whole number');
  expect(validateEvent({ ...pd, pd_result: 'pregnant', months_pregnant: '2.5' })).toContain('whole number');
});
