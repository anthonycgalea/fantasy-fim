export type DraftPick = {
    events: {
        event_key: string;
        week: number;
    }[];
    fantasy_team_id: number;
    pick_number: number;
    team_picked: string;
}