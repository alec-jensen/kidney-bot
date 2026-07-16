/** Styled inline error banner for API failures — never dump raw error text. */
export function ErrorBanner({ message }: { message: string }) {
  return (
    <div className="error-banner" role="alert">
      {message}
    </div>
  );
}
