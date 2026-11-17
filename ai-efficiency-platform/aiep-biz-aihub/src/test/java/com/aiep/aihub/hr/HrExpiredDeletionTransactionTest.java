package com.aiep.aihub.hr;

import static org.junit.jupiter.api.Assertions.*;
import static org.mockito.Mockito.*;

import com.aiep.aihub.api.hr.HrCandidateContracts.Candidate;
import com.aiep.aihub.application.hr.HrExpiredDeletionRegistrar;
import com.aiep.aihub.repository.hr.HrTalentMapper;
import org.h2.jdbcx.JdbcDataSource;
import org.junit.jupiter.api.Test;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.jdbc.datasource.DataSourceTransactionManager;

class HrExpiredDeletionTransactionTest {
  @Test
  void failure_after_tombstone_rolls_back_and_next_schedule_can_create_saga() {
    var ds = new JdbcDataSource();
    ds.setURL("jdbc:h2:mem:expired_" + System.nanoTime() + ";DB_CLOSE_DELAY=-1");
    var jdbc = new JdbcTemplate(ds);
    jdbc.execute("CREATE TABLE candidates(id VARCHAR(36) PRIMARY KEY,status VARCHAR(24))");
    jdbc.execute("CREATE TABLE jobs(candidate_id VARCHAR(36))");
    jdbc.update("INSERT INTO candidates VALUES('c','ACTIVE')");
    var mapper = mock(HrTalentMapper.class);
    when(mapper.tombstone("t", "c", 1))
        .thenAnswer(
            i ->
                jdbc.update(
                    "UPDATE candidates SET status='DELETING' WHERE id='c' AND status='ACTIVE'"));
    doThrow(new IllegalStateException("synthetic failure")).when(mapper).insertJob(any());
    var service = new HrExpiredDeletionRegistrar(mapper, new DataSourceTransactionManager(ds));
    var candidate = new Candidate("c", "t", "d", "s", 1);
    assertThrows(IllegalStateException.class, () -> service.register(candidate));
    assertEquals(
        "ACTIVE", jdbc.queryForObject("SELECT status FROM candidates WHERE id='c'", String.class));
    doAnswer(
            i -> {
              jdbc.update("INSERT INTO jobs VALUES('c')");
              return null;
            })
        .when(mapper)
        .insertJob(any());
    service.register(candidate);
    assertEquals(
        "DELETING",
        jdbc.queryForObject("SELECT status FROM candidates WHERE id='c'", String.class));
    assertEquals(1, jdbc.queryForObject("SELECT COUNT(*) FROM jobs", Integer.class));
  }
}
