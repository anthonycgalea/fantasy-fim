import { Link } from "@tanstack/react-router";

export const Navbar = () => {
  return (
    <nav className="w-full py-4 mb-4 border-b">
      <ul className="flex gap-4">
        <li>
          <Link to="/" className="hover:underline">
            Home
          </Link>
        </li>
        <li>
          <Link to="/eventData" className="hover:underline">
            Events
          </Link>
        </li>
        <li>
          <Link to="/leagues" className="hover:underline">
            Leagues
          </Link>
        </li>
        <li>
          <Link to="/offseasonDrafts" className="hover:underline">
            Offseason Drafts
          </Link>
        </li>
        <li>
          <a href="/apidocs" className="hover:underline">
            API
          </a>
        </li>
        <li>
          <a
            href="https://github.com/anthonycgalea/fantasy-fim"
            target="_blank"
            rel="noopener noreferrer"
            className="hover:underline"
          >
            GitHub
          </a>
        </li>
      </ul>
    </nav>
  );
};
export default Navbar;
