import { Link } from "react-router-dom";

export function NotFound() {
  return (
    <div className="centered-page">
      <h1>Page not found</h1>
      <p>The page you're looking for doesn't exist.</p>
      <Link className="button" to="/">
        Back home
      </Link>
    </div>
  );
}
