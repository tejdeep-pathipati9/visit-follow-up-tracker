export interface SearchAnswer {
  explanation: string;
  sql: string;
  result: {
    columns: string[];
    rows: (string | number | null)[][];
    row_count: number;
    truncated: boolean;
  };
}

export const clinicQuestions = [
  "Which doctor has the most overdue labs?",
  "Show overdue referrals assigned to Nurse Ana.",
  "List open follow-ups due in the next seven days.",
];
