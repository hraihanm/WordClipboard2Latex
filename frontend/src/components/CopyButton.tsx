import { useState, type MouseEvent } from 'react';

interface Props {
  text: string;
  /** Use inside <summary> so click does not toggle the parent <details>. */
  inSummary?: boolean;
}

export default function CopyButton({ text, inSummary }: Props) {
  const [copied, setCopied] = useState(false);

  const doCopy = async () => {
    try {
      await navigator.clipboard.writeText(text);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    } catch {
      // Fallback
      const textarea = document.createElement('textarea');
      textarea.value = text;
      document.body.appendChild(textarea);
      textarea.select();
      document.execCommand('copy');
      document.body.removeChild(textarea);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    }
  };

  const onMouseDown = inSummary
    ? (e: MouseEvent<HTMLButtonElement>) => e.stopPropagation()
    : undefined;

  const onClick = inSummary
    ? (e: MouseEvent<HTMLButtonElement>) => {
        e.stopPropagation();
        void doCopy();
      }
    : () => void doCopy();

  return (
    <button type="button" className="copy-btn" onMouseDown={onMouseDown} onClick={onClick} disabled={!text}>
      {copied ? 'Copied!' : 'Copy'}
    </button>
  );
}
