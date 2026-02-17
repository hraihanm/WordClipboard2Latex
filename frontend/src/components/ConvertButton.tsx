interface Props {
  onClick: () => void;
  loading: boolean;
}

export default function ConvertButton({ onClick, loading }: Props) {
  return (
    <button
      className="convert-btn"
      onClick={onClick}
      disabled={loading}
    >
      {loading ? (
        <>
          <span className="spinner" />
          Converting…
        </>
      ) : (
        'Convert Clipboard'
      )}
    </button>
  );
}
