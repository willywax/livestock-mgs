import { applyEventChange, blankEvent, eventFromApi, eventToCreatePayload, eventToUpdatePayload } from './EventForm';

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
