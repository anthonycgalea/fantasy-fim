export type AvailableTeam = {
  team_number: number;
  name: string;
  events: {
    event_key: string;
    week: number;
  }[];
  year_end_epa: number;
};
