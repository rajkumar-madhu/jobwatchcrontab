/* R74: where "talk to a human" goes. A booking link (Cal.com, Calendly, Google appointment page) set at
   build time as NEXT_PUBLIC_BOOKING_URL; otherwise the contact form, which stores the message for the team. */
export const BOOKING_URL = process.env.NEXT_PUBLIC_BOOKING_URL || "/contact";
export const TALK = BOOKING_URL.startsWith("http") ? "Book 20 minutes with the founder" : "Talk to a human";
