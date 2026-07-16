import { loginUrl } from "../lib/api";

export function Login() {
  return (
    <div className="centered-page">
      <h1>kidney-bot dashboard</h1>
      <p>Sign in with Discord to manage servers you have Manage Server access to.</p>
      <a className="button" href={loginUrl()}>
        Login with Discord
      </a>
    </div>
  );
}
