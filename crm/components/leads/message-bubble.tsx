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
              ? "bg-zinc-100 text-zinc-900 rounded-bl-sm dark:bg-zinc-900 dark:text-zinc-100"
              : "bg-zinc-50 text-zinc-700 rounded-br-sm border border-zinc-200 dark:bg-zinc-950 dark:text-zinc-300 dark:border-zinc-800",
          )}
        >
          {content}
        </div>
        <p
          className={cn(
            "mt-1 text-[10px] text-zinc-400",
            isUser ? "text-left" : "text-right",
          )}
        >
          {isUser ? "Cliente" : "Malu"} · {formatDateTime(createdAt)}
        </p>
      </div>
    </div>
  );
}
