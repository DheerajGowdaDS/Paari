export type TxStepVariant =
  | "default"
  | "governance"
  | "razorpay"
  | "verified"
  | "success";

export interface TxStep {
  icon: string;
  title: string;
  timestamp: string;
  desc: string;
  variant: TxStepVariant;
  extra?: string;
}

export const TX_STEPS: TxStep[] = [
  {
    icon: "person",
    title: "User request",
    timestamp: "2026-09-04T10:30:15",
    desc: 'User asked to buy "Nike Air Zoom Pegasus 40" size 8',
    variant: "default",
  },
  {
    icon: "smart_toy",
    title: "AI Buyer Agent",
    timestamp: "2026-09-04T10:30:16",
    desc: "Buyer agent BA-001 received the request and started planning",
    variant: "default",
  },
  {
    icon: "handshake",
    title: "A2A negotiation",
    timestamp: "2026-09-04T10:30:18",
    desc: "Buyer agent negotiating with merchant agent via A2A protocol",
    variant: "default",
  },
  {
    icon: "storefront",
    title: "Merchant Agent",
    timestamp: "2026-09-04T10:30:22",
    desc: "Merchant agent MA-001 responded with product, price & availability",
    variant: "default",
  },
  {
    icon: "description",
    title: "Final quote accepted",
    timestamp: "2026-09-04T10:30:28",
    desc: "Quote Q-001 accepted by buyer agent",
    variant: "default",
  },
  {
    icon: "credit_card",
    title: "Payment request",
    timestamp: "2026-09-04T10:30:30",
    desc: "Payment request sent to Paari Gateway",
    variant: "default",
  },
  {
    icon: "shield",
    title: "Paari Governance",
    timestamp: "2026-09-04T10:30:31",
    desc: "All governance checks passed",
    variant: "governance",
    extra: "Decision: ALLOW",
  },
  {
    icon: "/",
    title: "Razorpay payment",
    timestamp: "2026-09-04T10:30:33",
    desc: "Payment session created. Redirected to Razorpay",
    variant: "razorpay",
  },
  {
    icon: "verified",
    title: "Payment verified",
    timestamp: "2026-09-04T10:31:02",
    desc: "Razorpay webhook verified. Payment captured successfully",
    variant: "verified",
  },
  {
    icon: "package_2",
    title: "Merchant fulfilled",
    timestamp: "2026-09-04T10:31:05",
    desc: "Order created in Shopify. Fulfillment initiated.",
    variant: "success",
  },
];
