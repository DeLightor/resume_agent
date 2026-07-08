// frontend/src/types/personal.ts
// US-12: 个人信息管理类型

/** 联系信息 */
export interface ContactInfo {
  name: string;
  gender: string;
  birth_date: string;
  phone: string;
  email: string;
  location: string;
  website: string;
  github: string;
  linkedin: string;
}

/** 求职意向 */
export interface JobIntention {
  target_role: string;
  expected_salary: string;
  availability: string;
}

/** 教育背景单项 */
export interface EducationItem {
  school: string;
  degree: string;
  major: string;
  period: string;
}

/** 完整个人信息 */
export interface PersonalInfo {
  contact: ContactInfo;
  job_intention: JobIntention;
  education: EducationItem[];
  summary: string;
}

/** 创建空个人信息 */
export function emptyPersonalInfo(): PersonalInfo {
  return {
    contact: {
      name: '',
      gender: '',
      birth_date: '',
      phone: '',
      email: '',
      location: '',
      website: '',
      github: '',
      linkedin: '',
    },
    job_intention: {
      target_role: '',
      expected_salary: '',
      availability: '',
    },
    education: [],
    summary: '',
  };
}
