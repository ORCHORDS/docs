# Severity Classification Guide

## Overview
Severity classification is a critical framework for prioritizing incident response based on impact to customers and business operations. This guide standardizes how organizations assess and respond to issues across four severity levels.

## Severity Levels

### S1 - Critical Impact
**Customer Impact:** Complete service outage affecting all users, no workarounds available
**Revenue Impact:** Severe financial loss, 50%+ revenue disruption
**Examples:**
- Database corruption affecting entire platform
- Major security breach compromising user data
- Complete system failure during peak hours
**Response Time:** < 15 minutes

### S2 - High Impact
**Customer Impact:** Significant service degradation affecting majority of users
**Revenue Impact:** Moderate financial loss, 20-50% revenue disruption
**Examples:**
- Major feature unavailable for 80% of users
- Performance degradation affecting core functionality
- Data loss affecting multiple customers
**Response Time:** < 1 hour

### S3 - Medium Impact
**Customer Impact:** Limited service issues affecting subset of users
**Revenue Impact:** Minor financial impact, <20% revenue disruption
**Examples:**
- Minor UI bug affecting specific user groups
- Slow performance in non-critical features
- Documentation errors
**Response Time:** < 4 hours

### S4 - Low Impact
**Customer Impact:** Minimal inconvenience, easily workarounded
**Revenue Impact:** Negligible financial impact
**Examples:**
- Cosmetic display issues
- Minor typo in user interface
- Non-essential feature requests
**Response Time:** < 24 hours

## Implementation Best Practices
- Regular review and update of severity criteria
- Clear escalation paths for each level
- Training for all team members on classification standards
- Automated systems to support rapid classification
- Post-incident analysis to refine severity assessments
