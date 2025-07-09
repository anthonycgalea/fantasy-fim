import React, { useEffect, useState } from 'react';
import { Tab, Tabs, Table, Row, Col } from 'react-bootstrap';
import api, { fetchWithRetry } from '../api';
import './ScoresLineups.css';

const ScoresLineups = ({ leagueId }) => {
  const [lineups, setLineups] = useState([]);
  const [leagueInfo, setLeagueInfo] = useState({});
  const [weeklyScores, setWeeklyScores] = useState({});
  const [championshipTeams, setChampionshipTeams] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  useEffect(() => {
    const fetchData = async () => {
      try {
        const [lineupRes, leagueRes, champRes] = await Promise.all([
          fetchWithRetry(() => api.get(`/leagues/${leagueId}/lineups`)),
          fetchWithRetry(() => api.get(`/leagues/${leagueId}`)),
          fetchWithRetry(() => api.get(`/leagues/${leagueId}/statesTeams`))
        ]);
        setLineups(lineupRes.data);
        setLeagueInfo(leagueRes.data);
        setChampionshipTeams(champRes.data); // No year check
      } catch (err) {
        setError('Failed to fetch league data');
      }
    };

    fetchData();
  }, [leagueId]);

  useEffect(() => {
    const fetchWeeklyScores = async () => {
      const scores = {};
      try {
        const promises = lineups.map(({ week }) =>
          fetchWithRetry(() =>
            api.get(`/leagues/${leagueId}/fantasyScores/${week}`)
          ).then(response => {
            scores[week] = response.data;
          })
        );
        await Promise.all(promises);
        setWeeklyScores(scores);
      } catch (err) {
        setError('Failed to fetch weekly scores');
      } finally {
        setLoading(false);
      }
    };

    if (lineups.length > 0) {
      fetchWeeklyScores();
    }
  }, [lineups, leagueId]);

  if (loading) return <div>Loading...</div>;
  if (error) return <div>{error}</div>;

  const renderTeamTable = (fantasy_team, week) => {
    const weeklyStarts = week === 6 ? leagueInfo.weekly_starts + 1 : leagueInfo.weekly_starts;
    return (
      <Col xs={12} md={3} key={fantasy_team.fantasy_team_id} className="mb-3">
        <Table bordered hover>
          <thead>
            <tr>
              <th colSpan={2} className="table-secondary">{fantasy_team.fantasy_team_name}</th>
            </tr>
            <tr>
              <th className="table-secondary">Score</th>
              <td>{weeklyScores[week]?.find(score => score.fantasy_team_id === fantasy_team.fantasy_team_id)?.weekly_score || 0}</td>
            </tr>
            <tr>
              <th className="table-secondary">RP</th>
              <td>{weeklyScores[week]?.find(score => score.fantasy_team_id === fantasy_team.fantasy_team_id)?.rank_points || 0}</td>
            </tr>
            <tr>
              <th className="table-secondary">Team #</th>
              <th className="table-secondary">Score</th>
            </tr>
          </thead>
          <tbody>
            {Array.from({ length: weeklyStarts }, (_, index) => {
              const teamStarted = fantasy_team.teams[index] || { team_number: '' };
              const teamScoreData = weeklyScores[week]?.find(score =>
                score.teams.some(team => team.team_number === teamStarted.team_number)
              ) || { teams: [{ weekly_score: 0 }] };
              const matchingTeam = teamScoreData.teams.find(team => team.team_number === teamStarted.team_number);
              const weeklyScore = matchingTeam ? matchingTeam.weekly_score : 0;

              return (
                <tr key={index}>
                  <td>{teamStarted.team_number || ''}</td>
                  <td>{weeklyScore || 0}</td>
                </tr>
              );
            })}
          </tbody>
        </Table>
      </Col>
    );
  };

  return (
    <Tabs defaultActiveKey="1" id="lineups-tabs" className="mb-3">
      {lineups.map(({ week, fantasy_teams }) => {
        const isWeek6 = week === 6;

        const championshipRoundTeams = fantasy_teams.filter(ft =>
          championshipTeams.includes(parseInt(ft.fantasy_team_id))
        );

        const consolationRoundTeams = fantasy_teams.filter(ft =>
          !championshipTeams.includes(parseInt(ft.fantasy_team_id))
        );

        return (
          <Tab eventKey={week} title={isWeek6 ? 'MSC' : `Week ${week}`} key={week}>
            {isWeek6 ? (
              <>
                {/* Championship Round */}
                <h4 className='text-center'>Championship Round</h4>
                <Row className="justify-content-center">
                  {championshipRoundTeams.map(fantasy_team => renderTeamTable(fantasy_team, week))}
                </Row>

                {/* Consolation Round */}
                <h4 className='text-center'>Consolation Round</h4>
                <Row className="justify-content-center">
                  {consolationRoundTeams.map(fantasy_team => renderTeamTable(fantasy_team, week))}
                </Row>
              </>
            ) : (
              <Row className="justify-content-center">
                {fantasy_teams.map(fantasy_team => renderTeamTable(fantasy_team, week))}
              </Row>
            )}
          </Tab>
        );
      })}
    </Tabs>
  );
};

export default ScoresLineups;
