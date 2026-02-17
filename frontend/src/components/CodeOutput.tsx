interface Props {
  content: string;
  language: string;
}

export default function CodeOutput({ content, language }: Props) {
  return (
    <div className="code-output">
      <pre>
        <code className={`language-${language}`}>{content}</code>
      </pre>
    </div>
  );
}
