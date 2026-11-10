import { clsx } from "clsx";
import { twMerge } from "tailwind-merge";

export function cn(...inputs) {
  return twMerge(clsx(inputs));
}

export const EVENT_TYPES = {
  pd_test: { label: 'PD Test', color: 'bg-pink-100 text-pink-800', icon: 'Heart' },
  service: { label: 'Service / Mating', color: 'bg-pink-100 text-pink-800', icon: 'Heart' },
  birth: { label: 'Birth', color: 'bg-green-100 text-green-800', icon: 'Plus' },
  death: { label: 'Death', color: 'bg-red-100 text-red-800', icon: 'Minus' },
  sold: { label: 'Sold', color: 'bg-blue-100 text-blue-800', icon: 'CurrencyDollar' },
  missing: { label: 'Missing', color: 'bg-yellow-100 text-yellow-800', icon: 'Question' },
  gift_in: { label: 'Gift In', color: 'bg-purple-100 text-purple-800', icon: 'Gift' },
  gift_out: { label: 'Gift Out', color: 'bg-pink-100 text-pink-800', icon: 'Gift' },
  bought: { label: 'Bought', color: 'bg-cyan-100 text-cyan-800', icon: 'ShoppingCart' },
  transfer: { label: 'Transfer', color: 'bg-orange-100 text-orange-800', icon: 'ArrowsLeftRight' },
  category_change: { label: 'Category Change', color: 'bg-indigo-100 text-indigo-800', icon: 'ArrowsDownUp' },
  abortion: { label: 'Abortion', color: 'bg-gray-100 text-gray-800', icon: 'Note' },
  weaning: { label: 'Weaning', color: 'bg-teal-100 text-teal-800', icon: 'Baby' },
};

export const SPECIES_CONFIG = {
  cattle: { label: 'Ngombe (Cattle)', color: '#2D5A27', bgClass: 'bg-cattle/10', textClass: 'text-cattle' },
  sheep: { label: 'Kondoo (Sheep)', color: '#0284C7', bgClass: 'bg-sheep/10', textClass: 'text-sheep' },
  goat: { label: 'Mbuzi (Goat)', color: '#D97706', bgClass: 'bg-goat/10', textClass: 'text-goat' },
};

export const DEATH_CAUSES = [
  { value: 'disease', label: 'Disease' },
  { value: 'accident', label: 'Accident' },
  { value: 'predator', label: 'Predator Attack' },
  { value: 'poisoning', label: 'Poisoning' },
  { value: 'birth_complications', label: 'Birth Complications' },
  { value: 'old_age', label: 'Old Age' },
  { value: 'malnutrition', label: 'Malnutrition/Starvation' },
  { value: 'unknown', label: 'Unknown' },
];

export const ABORTION_STAGES = [
  { value: 'early', label: 'Early (0-3 months)' },
  { value: 'mid', label: 'Mid (3-6 months)' },
  { value: 'late', label: 'Late (6-9 months)' },
];

export const ROLES = {
  admin: { label: 'Admin', color: 'bg-purple-100 text-purple-800' },
  data_entry: { label: 'Data Entry', color: 'bg-blue-100 text-blue-800' },
  viewer: { label: 'Viewer', color: 'bg-gray-100 text-gray-800' },
};

export const formatDate = (date) => {
  if (!date) return '';
  return new Date(date).toLocaleDateString('en-GB', {
    day: '2-digit',
    month: 'short',
    year: 'numeric'
  });
};

export const formatDateTime = (date) => {
  if (!date) return '';
  return new Date(date).toLocaleString('en-GB', {
    day: '2-digit',
    month: 'short',
    year: 'numeric',
    hour: '2-digit',
    minute: '2-digit'
  });
};
