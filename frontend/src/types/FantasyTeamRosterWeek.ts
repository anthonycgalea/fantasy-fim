export type FantasyTeamRosterWeek = {
  fantasy_team_id: number;
  fantasy_team_name: string;
  roster: {
    team_key: string;
    events: {
      event_key: string;
      event_name: string;
      week: number;
    }[];
  }[];
};
