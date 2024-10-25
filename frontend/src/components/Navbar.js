// src/components/Navbar.js
import React from 'react';
import { Link } from 'react-router-dom'; // Import Link for navigation
import './Navbar.css'; // Import the CSS file for styles

const Navbar = () => {
  return (
    <nav className="navbar navbar-expand-lg navbar-light bg-light">
      <div className="container-fluid">
        <Link className="navbar-brand" to="/">Fantasy FiM</Link>
        <button className="navbar-toggler" type="button" data-bs-toggle="collapse" data-bs-target="#navbarNav" aria-controls="navbarNav" aria-expanded="false" aria-label="Toggle navigation">
          <span className="navbar-toggler-icon"></span>
        </button>
        <div className="collapse navbar-collapse" id="navbarNav">
          <ul className="navbar-nav">
            <li className="nav-item">
              <Link className="nav-link" to="/">Home</Link>
            </li>
            <li className="nav-item">
              <Link className="nav-link" to="/eventData">Events</Link>
            </li>
            <li className="nav-item">
              <Link className="nav-link" to="http://fantasyfim.com/api/apidocs">API</Link>
            </li>
            <li className="nav-item">
              <Link className="nav-link" to="https://github.com/anthonycgalea/fantasy-fim">GitHub</Link>
            </li>
          </ul>
        </div>
      </div>
    </nav>
  );
};

export default Navbar;
