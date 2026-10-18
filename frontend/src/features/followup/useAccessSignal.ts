import { useCrm } from "../../context/CrmContext";

export function useAccessSignal(contactId?: number | null, conversationId?: string | null): string {
  const { contactsById, conversations, selectedConversation, sessionUser, canSeeAll, perfil } = useCrm();
  const contact = contactId ? contactsById.get(contactId) : null;
  const thread = conversationId ? conversations.find((entry) => entry.id === conversationId) || (selectedConversation?.id === conversationId ? selectedConversation : null) : null;
  return JSON.stringify([
    sessionUser?.id, sessionUser?.role, canSeeAll, perfil,
    contact ? [contact.id, contact.assigned_to, contact.assigned_to_uid, contact.is_archived] : null,
    thread ? [thread.id, thread.assigned_to, thread.assigned_to_uid, thread.is_backup] : null,
  ]);
}
