import { cn } from "@/lib/utils";
import { formatDateTime } from "@/lib/format";

interface Props {
  role: "user" | "assistant";
  content: string;
  createdAt: string;
}

export function MessageBubble({ role, content, createdAt }: Props) {
  const isUser = role === "user";
  return (
    <div
      className={cn(
        "flex w-full",
        isUser ? "justify-start" : "justify-end",
      )}
    >
      <div className={cn("max-w-[85%] sm:max-w-[70%]")}>
        <div
          className={cn(
            "rounded-2xl px-3.5 py-2 text-sm whitespace-pre-wrap break-words",
            isUser
              ? "bg-muted text-foreground rounded-bl-sm"
              : "bg-card text-foreground/90 rounded-br-sm border border-border",
          )}
        >
          {content}
        </div>
        <p
          className={cn(
            "mt-1 text-[10px] text-muted-foreground/80",
            isUser ? "text-left" : "text-right",
          )}
        >
          {isUser ? "Cliente" : "Malu"} · {formatDateTime(createdAt)}
        </p>
      </div>
    </div>
  );
}
