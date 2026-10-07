import { useAuth } from "./context/AuthContext";
import ChatLayout from "./components/ChatLayout";
import EntryGate from "./components/EntryGate";
import { Spinner } from "./components/icons";

export default function App() {
  const { state } = useAuth();

  if (state.status === "loading") {
    return (
      <div className="flex h-full items-center justify-center text-mute" role="status">
        <Spinner size={22} />
        <span className="sr-only">Loading</span>
      </div>
    );
  }

  if (state.status === "anonymous") return <EntryGate />;

  // Keyed by user so a new sign-in always starts from clean state.
  return <ChatLayout key={state.user.id} user={state.user} />;
}
