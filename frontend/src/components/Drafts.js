// src/components/Drafts.js
import React, { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { useParams } from 'react-router-dom';
import api from '../api'; // Adjust the import path based on your project structure
import './Drafts.css'; // Import the CSS file for styles
import DraftScore from './DraftScore';

const Drafts = () => {
  const { draftId } = useParams(); // Get the draftId from the URL
  const [draft, setDraft] = useState(null);
  const [draftOrder, setDraftOrder] = useState([]);
  const [draftPicks, setDraftPicks] = useState([]);
  const [availableTeams, setAvailableTeams] = useState([]);
  const [fantasyTeams, setFantasyTeams] = useState([]); // State for fantasy team names
  const [league, setLeague] = useState(null)
  const [activeTab, setActiveTab] = useState('draftBoard'); // State for active tab
  const [selectedWeeks, setSelectedWeeks] = useState([1, 2, 3, 4, 5]); // Initially include all weeks

  useEffect(() => {
    const fetchDraftData = async () => {
      try {
        const draftResponse = await api.get(`/drafts/${draftId}`);
        const [orderResponse, picksResponse, availableTeamsResponse, leaguesResponse, fantasyTeamsResponse] = await Promise.all([
          api.get(`/drafts/${draftId}/draftOrder`),
          api.get(`/drafts/${draftId}/picks`),
          api.get(`/drafts/${draftId}/availableTeams`),
          api.get(`/leagues/${draftResponse.data.league_id}`),
          api.get(`/leagues/${draftResponse.data.league_id}/fantasyTeams`)
        ]);
        
        setDraft(draftResponse.data);
        setDraftOrder(orderResponse.data);
        setDraftPicks(picksResponse.data);
        setAvailableTeams(availableTeamsResponse.data);
        setLeague(leaguesResponse.data); 
        setFantasyTeams(fantasyTeamsResponse.data);
      } catch (error) {
        console.error('Error fetching draft data:', error);
      }
    };
  
    fetchDraftData();
  }, [draftId]);

  const toggleWeekSelection = (week) => {
    setSelectedWeeks((prevSelectedWeeks) =>
      prevSelectedWeeks.includes(week)
        ? prevSelectedWeeks.filter((w) => w !== week) // Remove if already selected
        : [...prevSelectedWeeks, week] // Add if not selected
    );
  };

  const renderWeeksDrafted = () => {
    // Initialize a dictionary to hold the count of drafted teams per week per fantasy team
    const fantasyTeamWeekCounts = {};
  
    // Populate the dictionary with fantasy team IDs as keys and arrays of zeros (one for each week)
    fantasyTeams.forEach((team) => {
      fantasyTeamWeekCounts[team.fantasy_team_id] = [0, 0, 0, 0, 0]; // One slot per week (weeks 1-5)
    });
  
    // Iterate over the draft picks to count how many teams were drafted for each week by each fantasy team
    draftPicks.forEach((pick) => {
      const fantasyTeamId = pick.fantasy_team_id;
      pick.events.forEach((event) => {
        const week = event.week; // Get the week from the event
        if (week >= 1 && week <= 5) {
          fantasyTeamWeekCounts[fantasyTeamId][week - 1] += 1; // Increment the count for the appropriate week
        }
      });
    });
  
    return (
      <table className="table table-bordered">
        <thead className='table-secondary'>
          <tr>
            <th>Fantasy Team</th>
            <th>Week 1</th>
            <th>Week 2</th>
            <th>Week 3</th>
            <th>Week 4</th>
            <th>Week 5</th>
          </tr>
        </thead>
        <tbody>
          {fantasyTeams.map((team) => (
            <tr key={team.fantasy_team_id}>
              <td>{team.team_name}</td>
              {/* Map each week's count for the current fantasy team */}
              {fantasyTeamWeekCounts[team.fantasy_team_id].map((count, index) => {

                let className = ''; // Determine the Bootstrap class based on the count and league weekly_starts
                
                if (count >= league.weekly_starts) {
                  className = 'table-success'; // If the exact number of required teams were drafted
                } else if (count === league.weekly_starts-1) {
                  className = 'table-warning'; // If almost about to draft the amount of needed teams drafted
                } else {
                  className = 'table-danger'; // If one less than the required number of teams were drafted
                }
  
                return (
                  <td key={index} className={className}>
                    {count}
                  </td>
                );
              })}
            </tr>
          ))}
        </tbody>
      </table>
    );
  };

  const renderAvailableTeams = () => {
    const weeks = [1, 2, 3, 4, 5]; // Define the weeks array here
  
    // Create a data structure to hold the events for each team by week, including year_end_epa
    const teamEventsByWeek = availableTeams.map((team) => {
      const events = weeks.map((week) => {
        const event = team.events.find((e) => e.week === week);
        return event ? event.event_key : ''; // Set event key or empty string
      });
      return { 
        teamNumber: team.team_number, 
        teamName: team.name,
        events, 
        yearEndEpa: team.year_end_epa // Include year_end_epa here
      };
    });
  
    let filteredTeams;
    if (league.is_fim) {
      // Filter teams based on selected weeks if league.is_fim is true
      filteredTeams = teamEventsByWeek.filter(({ events }) =>
        selectedWeeks.some((week) => events[week - 1] !== '') // Check if any selected week has an event
      );
    } else {
      // If league.is_fim is false, show all available teams without filtering
      filteredTeams = teamEventsByWeek;
    }
  
    const prevYear = league.year - 1;
    return (
      <table className="table table-bordered">
        <thead className='table-secondary'>
          <tr>
            <th rowSpan="2" className="align-middle">Team #</th>
            <th rowSpan="2" className="align-middle">Team Name</th>
            {league.is_fim && (
              <>
                <th colSpan="5">Week</th>
              </>
            )}
            <th rowSpan="2" className="align-middle">{league.is_fim ? prevYear : league.year} EPA</th>
          </tr>
          {league.is_fim && (
            <tr>
              {weeks.map((week) => (
                <th key={week}>
                  <div className="form-check form-switch d-flex justify-content-between align-items-center">
                    <label className="form-check-label">{`${week}`}</label>
                    <input
                      type="checkbox"
                      className="form-check-input"
                      checked={selectedWeeks.includes(week)}
                      onChange={() => toggleWeekSelection(week)}
                    />
                  </div>
                </th>
              ))}
            </tr>
          )}
        </thead>
        <tbody>
          {filteredTeams.map(({ teamNumber, teamName, events, yearEndEpa }) => (
            <tr key={teamNumber}>
              <td>{teamNumber}</td>
              <td>{teamName}</td>
              {league.is_fim && events.map((event, index) => (
                <td key={index}>{event}</td>
              ))}
              <td>{yearEndEpa}</td> {/* Display the year_end_epa */}
            </tr>
          ))}
        </tbody>
      </table>
    );
  };
  
  
  const renderDraftBoard = () => {
    const picksByRound = {};

    // Organize picks by round
    draftPicks.forEach((pick) => {
      const round = Math.floor((pick.pick_number - 1) / draftOrder.length) + 1; // Calculate round
      if (!picksByRound[round]) {
        picksByRound[round] = [];
      }
      picksByRound[round].push(pick);
    });
    
    const colWid = 50/draftOrder.length + "%";
    return (
      <table className="table table-bordered">
        <thead className='table-secondary'>
          <tr>
            <th className="text-wrap draft-round">Round</th> {/* Round column */}
            {draftOrder.map((order) => {
              const team = fantasyTeams.find(ft => ft.fantasy_team_id === order.fantasy_team_id);
              return (
                <th key={order.draft_slot} className="text-wrap" style={{width: colWid}}>{team ? team.team_name : `Team ${order.fantasy_team_id}`}</th>
              );
            })}
          </tr>
        </thead>
        <tbody>
          {Object.keys(picksByRound).map((round) => {
            const picks = picksByRound[round];
            return (
              <tr key={round}>
                <td className="text-wrap">{round}</td> {/* Displaying the round number */}
                {draftOrder.map((order) => {
                  const pick = picks.find(p => p.fantasy_team_id === order.fantasy_team_id);
                  return (
                    <td key={order.draft_slot}>
                      {pick.team_picked !== "-1" && pick.team_picked}
                    </td>
                  );
                })}
              </tr>
            );
          })}
        </tbody>
      </table>
    );
  };

  return (
    <div className="container mt-5">
      <div className="row">
      {draft ? ( // Check if draft is loaded
        <h2 className="text-center">{draft.event_key === "fim" ? "Michigan" : draft.event_key} Draft for <Link to={`/leagues/${league.league_id}`}>{league ? league.league_name : 'Loading...'}</Link></h2>
      ) : (
        <h2 className="text-center">Loading Draft...</h2> // Loading message if draft is not yet available
      )}
    </div>
    <ul className="nav nav-tabs">
      <li className="nav-item flex-fill">
        <button
          className={`nav-link ${activeTab === 'draftBoard' ? 'active' : ''}`}
          onClick={() => setActiveTab('draftBoard')}
        >
          Draft Board
        </button>
      </li>
      <li className="nav-item flex-fill">
        <button
          className={`nav-link ${activeTab === 'availableTeams' ? 'active' : ''}`}
          onClick={() => setActiveTab('availableTeams')}
        >
          Available Teams
        </button>
      </li>
      {league?.is_fim && (
        <li className="nav-item flex-fill">
          <button
            className={`nav-link ${activeTab === 'weeksDrafted' ? 'active' : ''}`}
            onClick={() => setActiveTab('weeksDrafted')}
          >
            Weeks Drafted
          </button>
        </li>
      )}
      {!league?.is_fim && (
        <li className="nav-item flex-fill">
        <button
          className={`nav-link ${activeTab === 'scores' ? 'active' : ''}`}
          onClick={() => setActiveTab('scores')}
        >
          Draft Score
        </button>
      </li>
      )}
    </ul>

      {activeTab === 'draftBoard' && (
        <div className="mt-3">
          {renderDraftBoard()}
        </div>
      )}
      {activeTab === 'availableTeams' && (
        <div className="mt-3">
          <div className="row">
            {renderAvailableTeams()}
          </div>
        </div>
      )}
      {activeTab === 'weeksDrafted' && (
        <div className="mt-3">
          <div className="row">
            {renderWeeksDrafted()}
          </div>
        </div>
      )}
      {activeTab === 'scores' && (
        <div className="mt-3">
          <div className="row">
            <DraftScore draftId={draftId} />
          </div>
        </div>
      )}
    </div>
  );
};

export default Drafts;
