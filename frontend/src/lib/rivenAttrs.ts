// Localized display names for riven attributes, keyed by the WFM slug as it
// arrives on auctions (v2-style: base_damage_/_melee_damage, heat_damage,
// damage_vs_grineer, fire_rate_/_attack_speed, ...). Unknown slugs fall back to
// a title-cased rendering so a new WFM attribute still shows something sane.
import { locale } from "../i18n";

function norm(slug: string): string {
  return slug.toLowerCase().trim().replace(/\s+/g, "_").replace(/-/g, "_");
}

const EN: Record<string, string> = {
  critical_chance: "Critical Chance",
  critical_damage: "Critical Damage",
  status_chance: "Status Chance",
  status_duration: "Status Duration",
  multishot: "Multishot",
  "base_damage_/_melee_damage": "Base / Melee Damage",
  "fire_rate_/_attack_speed": "Fire Rate / Attack Speed",
  cold_damage: "Cold",
  heat_damage: "Heat",
  electric_damage: "Electricity",
  toxin_damage: "Toxin",
  impact_damage: "Impact",
  puncture_damage: "Puncture",
  slash_damage: "Slash",
  damage_vs_grineer: "Damage to Grineer",
  damage_vs_corpus: "Damage to Corpus",
  damage_vs_infested: "Damage to Infested",
  ammo_maximum: "Ammo Maximum",
  magazine_capacity: "Magazine Capacity",
  punch_through: "Punch Through",
  projectile_speed: "Projectile Speed",
  recoil: "Recoil",
  reload_speed: "Reload Speed",
  zoom: "Zoom",
  range: "Range",
  combo_duration: "Combo Duration",
  channeling_damage: "Channeling Damage",
  channeling_efficiency: "Channeling Efficiency",
  chance_to_gain_combo_count: "Combo Chance",
  chance_to_gain_extra_combo_count: "Extra Combo Chance",
  finisher_damage: "Finisher Damage",
  critical_chance_on_slide_attack: "Slide Crit Chance",
};

const RU: Record<string, string> = {
  critical_chance: "Шанс крита",
  critical_damage: "Крит. урон",
  status_chance: "Шанс статуса",
  status_duration: "Длит. статуса",
  multishot: "Мультишот",
  "base_damage_/_melee_damage": "Урон / Урон ближнего боя",
  "fire_rate_/_attack_speed": "Скорострельность / Скор. атаки",
  cold_damage: "Холод",
  heat_damage: "Жар",
  electric_damage: "Электричество",
  toxin_damage: "Токсин",
  impact_damage: "Удар",
  puncture_damage: "Пробивание",
  slash_damage: "Разрез",
  damage_vs_grineer: "Урон по Гринир",
  damage_vs_corpus: "Урон по Корпус",
  damage_vs_infested: "Урон по Заражённым",
  ammo_maximum: "Макс. боезапас",
  magazine_capacity: "Ёмкость магазина",
  punch_through: "Сквозное пробитие",
  projectile_speed: "Скорость снаряда",
  recoil: "Отдача",
  reload_speed: "Скор. перезарядки",
  zoom: "Прицеливание",
  range: "Дальность",
  combo_duration: "Длит. комбо",
  channeling_damage: "Урон канала",
  channeling_efficiency: "Эффект. канала",
  chance_to_gain_combo_count: "Шанс комбо",
  chance_to_gain_extra_combo_count: "Шанс доп. комбо",
  finisher_damage: "Урон добивания",
  critical_chance_on_slide_attack: "Крит. шанс в скольжении",
};

function fallback(slug: string): string {
  return slug.replace(/_/g, " ").replace(/\b\w/g, (c) => c.toUpperCase());
}

/** Localized riven attribute name for the current locale (RU/EN), slug-keyed. */
export function rivenAttrName(slug: string): string {
  const key = norm(slug);
  const map = locale() === "ru" ? RU : EN;
  return map[key] ?? EN[key] ?? fallback(slug);
}
