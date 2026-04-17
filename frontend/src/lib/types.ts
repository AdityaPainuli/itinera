export type TravelStyle =
  | "cultural"
  | "adventure"
  | "food"
  | "relaxation"
  | "nature"
  | "spiritual"
  | "shopping"
  | "nightlife"
  | "photography"
  | "family";

export interface ItineraryRequest {
  destination: string;
  duration_days: number;
  budget_inr: number;
  travelers: number;
  travel_styles: TravelStyle[];
  special_instructions?: string;
  start_date?: string;
}

export interface Activity {
  name: string;
  description: string;
  duration_minutes: number;
  cost_inr: number;
  location: string;
  tips?: string;
  source_urls: string[];
}

export interface MealSuggestion {
  meal: "breakfast" | "lunch" | "dinner" | "snack";
  place: string;
  cuisine: string;
  cost_inr: number;
  notes?: string;
}

export interface DayPlan {
  day_number: number;
  theme: string;
  morning: Activity[];
  afternoon: Activity[];
  evening: Activity[];
  meals: MealSuggestion[];
  daily_cost_estimate_inr: number;
}

export interface Accommodation {
  name: string;
  area: string;
  type: "hotel" | "homestay" | "hostel" | "resort" | "guesthouse" | "airbnb";
  price_per_night_inr: number;
  rating?: number;
  why: string;
}

export interface CostBreakdown {
  accommodation_inr: number;
  food_inr: number;
  activities_inr: number;
  transport_inr: number;
  miscellaneous_inr: number;
  total_inr: number;
  fits_budget: boolean;
  notes?: string;
}

export interface Itinerary {
  id?: string;
  request: ItineraryRequest;
  summary: string;
  best_time_to_visit: string;
  getting_there: string;
  local_transportation: string;
  days: DayPlan[];
  accommodation_suggestions: Accommodation[];
  cost_breakdown: CostBreakdown;
  packing_list: string[];
  local_tips: string[];
  cautions: string[];
  sources: string[];
  created_at?: string;
}

export interface ItineraryListItem {
  id: string;
  destination: string;
  duration_days: number;
  summary: string;
  created_at: string;
}
