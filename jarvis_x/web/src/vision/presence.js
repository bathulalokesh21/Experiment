// Presence from the face count (faces are counted, never identified). Pure and testable.
export class PresenceTracker {
  constructor({ awayAfter = 300, arriveAfterAbsent = 8, friendStable = 2.5 } = {}) {
    this.awayAfter = awayAfter; this.arriveAfterAbsent = arriveAfterAbsent; this.friendStable = friendStable;
    this.present = false; this.lastSeen = null; this.absentSince = null; this.greeted = false; this.away = false;
    this.people = 0; this.candidate = 0; this.candidateSince = 0; this.friendGreeted = false; this.started = null;
  }
  /** update(faceCount, tSeconds) -> events: arrive, away, return, friend, people */
  update(count, t) {
    const events = [];
    if (this.started == null) { this.started = t; this.absentSince = t; }
    // debounce the people count so one flickering detection doesn't announce a visitor
    if (count !== this.candidate) { this.candidate = count; this.candidateSince = t; }
    const stable = t - this.candidateSince >= (count > this.people ? this.friendStable : 1.2);
    if (stable && count !== this.people) {
      const before = this.people;
      this.people = count;
      events.push({ type: 'people', count });
      if (count >= 2 && before === 1 && !this.friendGreeted) { this.friendGreeted = true; events.push({ type: 'friend', count }); }
    }
    if (count > 0) {
      if (!this.present) {
        const absentFor = this.absentSince == null ? 0 : t - this.absentSince;
        this.present = true;
        if (this.away) { this.away = false; events.push({ type: 'return' }); }
        else if (!this.greeted && (absentFor >= this.arriveAfterAbsent || t - this.started < 3)) { this.greeted = true; events.push({ type: 'arrive' }); }
      }
      this.lastSeen = t; this.absentSince = null;
    } else {
      if (this.present) { this.present = false; this.absentSince = t; }
      if (!this.away && this.absentSince != null && t - this.absentSince >= this.awayAfter && this.lastSeen != null) { this.away = true; events.push({ type: 'away' }); }
    }
    return events;
  }
}
