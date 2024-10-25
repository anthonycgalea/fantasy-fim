import React, { useEffect, useState } from 'react';
import api from '../api';
import { Table, Spinner, Alert } from 'react-bootstrap';

const EventStatboticsData = () => {
  const [eventData, setEventData] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [sortConfig, setSortConfig] = useState({ key: 'event_name', direction: 'ascending' });

  useEffect(() => {
    const fetchEventData = async () => {
      try {
        const response = await api.get('/fimeventdata');
        setEventData(response.data);
      } catch (err) {
        setError(err.message);
      } finally {
        setLoading(false);
      }
    };

    fetchEventData();
  }, []);

  const sortedEventData = React.useMemo(() => {
    let sortableItems = [...eventData];
    if (sortConfig !== null) {
      sortableItems.sort((a, b) => {
        if (a[sortConfig.key] < b[sortConfig.key]) {
          return sortConfig.direction === 'ascending' ? -1 : 1;
        }
        if (a[sortConfig.key] > b[sortConfig.key]) {
          return sortConfig.direction === 'ascending' ? 1 : -1;
        }
        return 0;
      });
    }
    return sortableItems;
  }, [eventData, sortConfig]);

  const requestSort = (key) => {
    let direction = 'ascending';
    if (sortConfig.key === key && sortConfig.direction === 'ascending') {
      direction = 'descending';
    }
    setSortConfig({ key, direction });
  };

  const getSortArrow = (key) => {
    if (sortConfig.key === key) {
      return sortConfig.direction === 'ascending' ? ' ▲' : ' ▼';
    }
    return '';
  };

  if (loading) {
    return <Spinner animation="border" role="status"><span className="visually-hidden">Loading...</span></Spinner>;
  }

  if (error) {
    return <Alert variant="danger">Error: {error}</Alert>;
  }

  return (
    <div className="container mt-5">
        <Table striped bordered hover responsive>
        <thead>
            <tr>
            <th onClick={() => requestSort('event_name')}>Event Name{getSortArrow('event_name')}</th>
            <th onClick={() => requestSort('teamcount')}>Team Count{getSortArrow('teamcount')}</th>
            <th onClick={() => requestSort('maxepa')}>Max EPA{getSortArrow('maxepa')}</th>
            <th onClick={() => requestSort('top8epa')}>EPA 8{getSortArrow('top8epa')}</th>
            <th onClick={() => requestSort('top24epa')}>EPA 24{getSortArrow('top24epa')}</th>
            <th onClick={() => requestSort('avgepa')}>Average EPA{getSortArrow('avgepa')}</th>
            <th onClick={() => requestSort('medianepa')}>Median EPA{getSortArrow('medianepa')}</th>
            </tr>
        </thead>
        <tbody>
            {sortedEventData.map((event, index) => (
                <tr key={index}>
                <td>{event.event_name}</td>
                <td>{event.teamcount}</td>
                <td>{event.maxepa}</td>
                <td>{event.top8epa}</td>
                <td>{event.top24epa}</td>
                <td>{Math.round(event.avgepa)}</td>
                <td>{event.medianepa}</td>
            </tr>
            ))}
        </tbody>
        </Table>
    </div>
  );
};

export default EventStatboticsData;
