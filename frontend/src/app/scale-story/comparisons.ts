export const LAND_ANIMALS_2024 = 87_892_277_479;
export const FISH_2019 = [1_058_000_000_000, 2_071_000_000_000] as const;
export const PEOPLE_2024 = 8_200_000_000;
export const FAUCET_DRIP_ML = .25;
export const REFERENCE_POOL_LITRES = 50 * 25 * 2.5 * 1000;
export const litresForIndividuals = (individuals: number) => individuals * FAUCET_DRIP_ML / 1000;
export const poolsForIndividuals = (individuals: number) => litresForIndividuals(individuals) / REFERENCE_POOL_LITRES;
export const populationDays = (individualsPerYear: number, daysInYear: number) => PEOPLE_2024 / individualsPerYear * daysInYear;
export const oneSecondEachYears = (individuals: number) => individuals / (365.2425 * 86400);
