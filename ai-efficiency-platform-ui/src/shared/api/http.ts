import axios, { type AxiosInstance } from 'axios';

export function createHttpClient(baseURL: string): AxiosInstance {
  return axios.create({
    baseURL,
    timeout: 10_000,
  });
}
