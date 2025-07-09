import React from 'react';
import { Card, CardContent, CardHeader } from './ui/card';
import { useRosters } from '@/api/useRosters';
import { useLeague } from '@/api/useLeague';
import { useTeamAvatar } from '@/api/useTeamAvatar';

const RosterTeamCard = ({ teamKey, year }) => {
  const teamNumber = teamKey.replace('frc', '');
  const teamAvatar = useTeamAvatar(teamKey, year);

  return (
    <a
      href={`https://www.thebluealliance.com/team/${teamNumber}/${year}`}
      target="_blank"
      className="p-2 border rounded-xl h-16 flex flex-col relative bg-slate-700 hover:bg-slate-800 cursor-pointer text-start"
    >
      <p className="text-xl font-bold">{teamNumber}</p>
      {teamAvatar.data?.image && (
        <img
          src={`data:image/png;base64,${teamAvatar.data.image}`}
          className="aspect-square h-1/2 absolute bottom-0 right-0 rounded"
        />
      )}
    </a>
  );
};

const Rosters = ({ leagueId }) => {
  const rosters = useRosters(leagueId);
  const league = useLeague(leagueId);

  if (rosters.isLoading || league.isLoading) {
    return <div>Loading...</div>;
  }

  return (
    <div className="grid grid-cols-2 gap-4">
      {rosters.data?.map((team) => (
        <Card key={team.fantasy_team_id}>
          <CardHeader>{team.fantasy_team_name}</CardHeader>
          <CardContent>
            <div className="grid grid-cols-3 gap-2">
              {team.roster.map((r) => (
                <RosterTeamCard key={r} teamKey={r} year={league.data?.year} />
              ))}
            </div>
          </CardContent>
        </Card>
      ))}
    </div>
  );
};

export default Rosters;
